"""SQLite storage: tickets, an outbox, and an append-only audit log."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets(
  id INTEGER PRIMARY KEY, external_id TEXT UNIQUE, channel TEXT NOT NULL, sender TEXT NOT NULL,
  message TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL UNIQUE REFERENCES tickets(id),
  recipient TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
"""
OPEN = ("pending_approval", "escalated")


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:  # commit on success, roll back on error
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
        data["result"] = json.loads(data["result"])
        return data

    def find_external(self, external_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM tickets WHERE external_id=?", (external_id,)).fetchone()
        return self._ticket(row) if row else None

    def create(self, message, sender, channel, result, external_id=None) -> dict:
        try:
            with self._db() as db:
                ticket_id = db.execute(
                    "INSERT INTO tickets(external_id,channel,sender,message,status,result,created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (external_id, channel, sender, message, result["status"], json.dumps(result), now())
                ).lastrowid
                self._event(db, ticket_id, "pipeline", result["status"], ",".join(result["flags"]))
        except sqlite3.IntegrityError:
            # The same webhook arrived twice at once: return the first ticket.
            existing = self.find_external(external_id) if external_id else None
            if existing:
                return self.get(existing["id"])
            raise
        return self.get(ticket_id)

    def get(self, ticket_id: int) -> dict:
        with self._db() as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not row:
                raise NotFound(f"No ticket {ticket_id}")
            events = db.execute("SELECT actor,action,detail,created_at FROM events "
                                "WHERE ticket_id=? ORDER BY id", (ticket_id,)).fetchall()
        return {**self._ticket(row), "events": [dict(e) for e in events]}

    def list(self, status: str | None = None, limit: int = 100) -> list[dict]:
        query, args = "SELECT * FROM tickets", []
        if status == "open":
            query, args = query + " WHERE status IN (?,?)", list(OPEN)
        elif status:
            query, args = query + " WHERE status=?", [status]
        with self._db() as db:
            rows = db.execute(query + " ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
        return [self._ticket(r) for r in rows]

    def decide(self, ticket_id: int, decision: str, reviewer: str, reply: str | None = None) -> dict:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("reviewer name is required")
        if reply is not None and not isinstance(reply, str):
            raise ValueError("reply must be text")
        ticket = self.get(ticket_id)
        body = (reply if reply is not None else ticket["result"]["draft"]).strip()
        if decision == "approve" and not body:
            raise ValueError("reply cannot be empty")
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
        return self.get(ticket_id)

    def outbox(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT 100")]

    def stats(self) -> dict:
        tickets = self.list(limit=10_000)
        by_status, by_intent = {}, {}
        for t in tickets:
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
            intent = t["result"]["triage"]["intent"]
            by_intent[intent] = by_intent.get(intent, 0) + 1
        with self._db() as db:
            sent, edited = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(detail='edited'),0) FROM events WHERE action='sent'").fetchone()
        latencies = [t["result"]["metrics"]["latency_ms"] for t in tickets]
        return {
            "tickets": len(tickets), "by_status": by_status, "by_intent": by_intent,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "model_cost_usd": round(sum(t["result"]["metrics"]["cost_usd"] for t in tickets), 6),
            "approved_unedited_rate": round((sent - edited) / sent, 3) if sent else None,
        }
