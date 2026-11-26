"""Storage for tickets, sent replies and an append-only audit log.

SQLite for local use. Postgres (set DATABASE_URL) for hosting, where each visitor's
data is kept apart by a workspace id.
"""
import csv
import io
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS tickets(
      id {id}, workspace TEXT NOT NULL, external_id TEXT, channel TEXT NOT NULL, sender TEXT NOT NULL,
      message TEXT NOT NULL, status TEXT NOT NULL, intent TEXT NOT NULL,
      latency_ms DOUBLE PRECISION NOT NULL, cost_usd DOUBLE PRECISION NOT NULL,
      result TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workspace, external_id))""",
    """CREATE TABLE IF NOT EXISTS outbox(
      id {id}, ticket_id BIGINT NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE,
      recipient TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS events(
      id {id}, ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
      actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS hits(
      bucket TEXT NOT NULL, window_start BIGINT NOT NULL, total INTEGER NOT NULL,
      PRIMARY KEY(bucket, window_start))""",
    "CREATE INDEX IF NOT EXISTS tickets_workspace ON tickets(workspace, id)",
    "CREATE INDEX IF NOT EXISTS tickets_created ON tickets(created_at)",
    "CREATE INDEX IF NOT EXISTS events_ticket ON events(ticket_id)",
]
OPEN = ("pending_approval", "escalated")


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Postgres:
    """Lets the same "?" SQL run on psycopg."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        return self.connection.execute(sql.replace("?", "%s"), args)


class Store:
    def __init__(self, path: str, database_url: str = ""):
        self.path, self.url = path, database_url
        self._local = threading.local()
        self._unique_errors: tuple = (sqlite3.IntegrityError,)
        if database_url:
            import psycopg  # only needed when hosted

            self._unique_errors = (psycopg.errors.UniqueViolation,)
        with self._db() as db:
            for statement in SCHEMA:
                db.execute(statement.format(
                    id="BIGSERIAL PRIMARY KEY" if database_url else "INTEGER PRIMARY KEY AUTOINCREMENT"))

    def _postgres(self):
        """One connection per thread, reused between requests to avoid reconnect delays."""
        import psycopg
        from psycopg.rows import dict_row

        held = getattr(self._local, "connection", None)
        if held is not None and not held.closed:
            if time.monotonic() - self._local.used < 30:
                return held
            try:
                held.execute("SELECT 1")
                return held
            except psycopg.Error:
                held.close()
        self._local.connection = psycopg.connect(
            self.url, autocommit=True, row_factory=dict_row, prepare_threshold=None, connect_timeout=10)
        return self._local.connection

    @contextmanager
    def _db(self):
        """A transaction: commits on success, rolls back on error."""
        if self.url:
            connection = self._postgres()
            with connection.transaction():
                yield _Postgres(connection)
            self._local.used = time.monotonic()
            return
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _event(db, ticket_id, actor, action, detail=""):
        db.execute("INSERT INTO events(ticket_id,actor,action,detail,created_at) VALUES(?,?,?,?,?)",
                   (ticket_id, actor, action, detail, now()))

    @staticmethod
    def _ticket(row) -> dict:
        data = dict(row)
        data.pop("workspace", None)
        data["result"] = json.loads(data["result"])
        return data

    def find_external(self, external_id: str, workspace="local") -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT id FROM tickets WHERE workspace=? AND external_id=?",
                             (workspace, external_id)).fetchone()
        return self.get(row["id"], workspace) if row else None

    def count(self, workspace: str | None = None) -> int:
        sql, args = "SELECT COUNT(*) AS n FROM tickets", ()
        if workspace is not None:
            sql, args = sql + " WHERE workspace=?", (workspace,)
        with self._db() as db:
            return db.execute(sql, args).fetchone()["n"]

    def create(self, message, sender, channel, result, external_id=None, workspace="local") -> dict:
        try:
            with self._db() as db:
                ticket_id = db.execute(
                    "INSERT INTO tickets(workspace,external_id,channel,sender,message,status,intent,"
                    "latency_ms,cost_usd,result,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
                    (workspace, external_id, channel, sender, message, result["status"],
                     result["triage"]["intent"], result["metrics"]["latency_ms"],
                     result["metrics"]["cost_usd"], json.dumps(result), now())
                ).fetchall()[0]["id"]
                self._event(db, ticket_id, "pipeline", result["status"], ",".join(result["flags"]))
        except self._unique_errors:
            # The same webhook arrived twice at once: return the first ticket.
            existing = self.find_external(external_id, workspace) if external_id else None
            if existing:
                return existing
            raise
        return self.get(ticket_id, workspace)

    def get(self, ticket_id: int, workspace="local") -> dict:
        with self._db() as db:
            row = db.execute("SELECT * FROM tickets WHERE id=? AND workspace=?",
                             (ticket_id, workspace)).fetchone()
            if not row:
                raise NotFound(f"No ticket {ticket_id}")
            events = db.execute("SELECT actor,action,detail,created_at FROM events "
                                "WHERE ticket_id=? ORDER BY id", (ticket_id,)).fetchall()
            sent = db.execute("SELECT body FROM outbox WHERE ticket_id=?", (ticket_id,)).fetchone()
        return {**self._ticket(row), "events": [dict(e) for e in events],
                "sent_reply": sent["body"] if sent else None}

    def list_tickets(self, status: str | None = None, limit: int = 100, workspace="local") -> list[dict]:
        query, args = "SELECT * FROM tickets WHERE workspace=?", [workspace]
        if status == "open":
            query, args = query + " AND status IN (?,?)", args + list(OPEN)
        elif status:
            query, args = query + " AND status=?", args + [status]
        with self._db() as db:
            rows = db.execute(query + " ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
        return [self._ticket(r) for r in rows]

    def snapshot(self, workspace="local", limit: int = 200) -> dict:
        """Everything the dashboard needs, in one transaction."""
        with self._db() as db:
            rows = db.execute(
                "SELECT id,channel,sender,message,status,intent,result,created_at FROM tickets "
                "WHERE workspace=? ORDER BY CASE WHEN status IN (?,?) THEN 0 ELSE 1 END, id DESC LIMIT ?",
                (workspace, *OPEN, limit)).fetchall()
            stats = self._stats(db, workspace)
        tickets = []
        for row in rows:
            item = dict(row)
            result = json.loads(item.pop("result"))
            item["message"] = item["message"][:160]
            item["urgency"] = result["triage"]["urgency"]
            item["flags"] = result["flags"]
            tickets.append(item)
        return {"tickets": tickets, "stats": stats}

    def decide(self, ticket_id: int, decision: str, reviewer: str, reply: str | None = None,
               workspace="local", acknowledged: bool = False) -> dict:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
            raise ValueError("reviewer name is required (up to 100 characters)")
        if reply is not None and (not isinstance(reply, str) or len(reply) > 4000):
            raise ValueError("reply must be text up to 4000 characters")
        ticket = self.get(ticket_id, workspace)
        body = (reply if reply is not None else ticket["result"]["draft"]).strip()
        if decision == "approve" and not body:
            raise ValueError("reply cannot be empty")
        if decision == "approve" and ticket["status"] == "escalated" and acknowledged is not True:
            raise ValueError("escalated ticket: confirm you checked the warnings (acknowledged: true)")
        new_status = "sent" if decision == "approve" else "rejected"
        with self._db() as db:
            # Conditional update, so two reviewers cannot both send the same reply.
            changed = db.execute("UPDATE tickets SET status=? WHERE id=? AND status IN (?,?)",
                                 (new_status, ticket_id, *OPEN)).rowcount
            if not changed:
                raise Conflict(f"Ticket {ticket_id} was already handled")
            if decision == "approve":
                db.execute("INSERT INTO outbox(ticket_id,recipient,body,created_at) VALUES(?,?,?,?)",
                           (ticket_id, ticket["sender"], body, now()))
            edited = decision == "approve" and body != ticket["result"]["draft"].strip()
            self._event(db, ticket_id, reviewer.strip(), new_status, "edited" if edited else "")
        return self.get(ticket_id, workspace)

    def outbox(self, workspace="local") -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT o.id,o.ticket_id,o.recipient,o.body,o.created_at FROM outbox o "
                "JOIN tickets t ON t.id=o.ticket_id WHERE t.workspace=? ORDER BY o.id DESC LIMIT 100",
                (workspace,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _stats(db, workspace) -> dict:
        groups = db.execute(
            "SELECT status,intent,COUNT(*) AS n,SUM(latency_ms) AS ms,SUM(cost_usd) AS cost "
            "FROM tickets WHERE workspace=? GROUP BY status,intent", (workspace,)).fetchall()
        reviews = db.execute(
            "SELECT COUNT(*) AS sent, SUM(CASE WHEN e.detail='edited' THEN 1 ELSE 0 END) AS edited "
            "FROM events e JOIN tickets t ON t.id=e.ticket_id WHERE t.workspace=? AND e.action='sent'",
            (workspace,)).fetchone()
        by_status, by_intent, total, latency, cost = {}, {}, 0, 0.0, 0.0
        for g in groups:
            by_status[g["status"]] = by_status.get(g["status"], 0) + g["n"]
            by_intent[g["intent"]] = by_intent.get(g["intent"], 0) + g["n"]
            total += g["n"]
            latency += g["ms"]
            cost += g["cost"]
        sent = reviews["sent"]
        return {
            "tickets": total, "by_status": by_status, "by_intent": by_intent,
            "avg_latency_ms": round(latency / total, 2) if total else 0,
            "model_cost_usd": round(cost, 6),
            "approved_unedited_rate": round((sent - reviews["edited"]) / sent, 3) if sent else None,
        }

    def stats(self, workspace="local") -> dict:
        with self._db() as db:
            return self._stats(db, workspace)

    def activity(self, workspace="local", limit: int = 200) -> list[dict]:
        """The audit log, newest first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT e.created_at,e.ticket_id,t.sender,e.actor,e.action,e.detail FROM events e "
                "JOIN tickets t ON t.id=e.ticket_id WHERE t.workspace=? ORDER BY e.id DESC LIMIT ?",
                (workspace, limit)).fetchall()
        return [dict(r) for r in rows]

    def audit_csv(self, workspace="local") -> str:
        rows = reversed(self.activity(workspace, 5000))
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        columns = ("created_at", "ticket_id", "sender", "actor", "action", "detail")
        writer.writerow(columns)
        for row in rows:
            # A leading = + - @ would be run as a formula by spreadsheet programs.
            writer.writerow([f"'{v}" if isinstance(v, str) and v[:1] in "=+-@\t\r" and v else v
                             for v in (row[c] for c in columns)])
        return out.getvalue()

    def reset(self, workspace="local") -> None:
        with self._db() as db:
            db.execute("DELETE FROM tickets WHERE workspace=?", (workspace,))

    def purge(self, hours: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self._db() as db:
            db.execute("DELETE FROM tickets WHERE created_at<?", (cutoff,))
            db.execute("DELETE FROM hits WHERE window_start<?", (int(time.time()) - 3600,))

    def hit(self, bucket: str) -> int:
        """Count one request in the current minute and return the total so far."""
        window = int(time.time()) // 60 * 60
        with self._db() as db:
            return db.execute(
                "INSERT INTO hits(bucket,window_start,total) VALUES(?,?,1) "
                "ON CONFLICT(bucket,window_start) DO UPDATE SET total=hits.total+1 RETURNING total",
                (bucket, window)).fetchall()[0]["total"]
