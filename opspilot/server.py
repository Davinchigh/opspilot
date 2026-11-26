"""JSON API and review dashboard (standard library HTTP server)."""
import hmac
import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import evaluate
from .config import Settings
from .service import Service
from .store import Conflict, NotFound

PUBLIC = Path(__file__).resolve().parent.parent / "public"
STATIC = {
    "/": ("index.html", "text/html"),
    "/app.css": ("app.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
LOCAL = {"127.0.0.1", "localhost", "::1"}
WORKSPACE = re.compile(r"[a-f0-9]{32}")
MAX_BODY = 32_000
DRAIN_LIMIT = 1_000_000


class TooMany(Exception):
    pass


def make_handler(service: Service, settings: Settings) -> type[BaseHTTPRequestHandler]:
    cache: dict = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = 30

        def _send(self, code, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            if settings.token:
                given = self.headers.get("Authorization", "").encode()
                return hmac.compare_digest(given, f"Bearer {settings.token}".encode())
            if settings.demo:
                return True
            # Without a token, only answer to local host names (blocks DNS rebinding).
            name = urlparse("//" + self.headers.get("Host", "")).hostname
            return name in LOCAL

        def _workspace(self) -> str:
            if not settings.demo:
                return "local"
            workspace = self.headers.get("X-Workspace", "")
            if not WORKSPACE.fullmatch(workspace):
                raise ValueError("send an X-Workspace header: 32 characters, 0-9 and a-f")
            return workspace

        def _limit(self):
            if not settings.rate_per_minute:
                return
            # x-real-ip is set by the hosting proxy; the socket address is used locally.
            address = self.headers.get("x-real-ip") if settings.demo else None
            address = address or self.client_address[0]
            if service.store.hit(f"ip:{address}") > settings.rate_per_minute:
                raise TooMany("Too many requests. Wait a minute and try again.")

        def _body(self) -> dict:
            # Requiring JSON stops plain cross-site form posts.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ValueError("Content-Type must be application/json")
            if not self.raw:
                raise ValueError("request body is empty or too large")
            data = json.loads(self.raw)
            if not isinstance(data, dict):
                raise ValueError("request body must be a JSON object")
            return data

        def _get(self, path, query):
            store = service.store
            if path == "/api/knowledge":
                return self._send(200, [{"id": c.id, "text": c.text} for c in service.pipeline.index.chunks])
            if path == "/api/search":
                return self._send(200, service.search(query.get("q", [""])[0][:500]))
            if path == "/api/evals":
                if "evals" not in cache:
                    cache["evals"] = evaluate.baseline(settings)
                return self._send(200, cache["evals"])
            workspace = self._workspace()
            if path == "/api/state":
                mode = {"provider": "openai" if service.pipeline.client else "offline",
                        "model": settings.model if service.pipeline.client else "",
                        "demo": settings.demo}
                return self._send(200, {"mode": mode, **store.snapshot(workspace)})
            if path == "/api/tickets":
                return self._send(200, store.list_tickets(query.get("status", [None])[0], workspace=workspace))
            if path == "/api/stats":
                return self._send(200, store.stats(workspace))
            if path == "/api/outbox":
                return self._send(200, store.outbox(workspace))
            if path == "/api/activity":
                return self._send(200, store.activity(workspace))
            if path == "/api/audit.csv":
                return self._send(200, store.audit_csv(workspace).encode(), "text/csv")
            ticket = re.fullmatch(r"/api/tickets/(\d{1,12})", path)
            if ticket:
                return self._send(200, store.get(int(ticket.group(1)), workspace))
            self._send(404, {"error": "not found"})

        def _post(self, path):
            ticket = re.fullmatch(r"/api/tickets/(\d{1,12})/decision", path)
            if not (ticket or path in ("/api/messages", "/api/reset")):
                return self._send(404, {"error": "not found"})
            workspace = self._workspace()
            self._limit()
            data = self._body()
            if path == "/api/messages":
                return self._send(201, service.submit(
                    data.get("message"), data.get("sender", "unknown"),
                    data.get("channel", "web"), data.get("external_id"), workspace))
            if path == "/api/reset":
                service.store.reset(workspace)
                return self._send(200, {"ok": True})
            self._send(200, service.store.decide(
                int(ticket.group(1)), data.get("decision"), data.get("reviewer"), data.get("reply"),
                workspace, data.get("acknowledged", False)))

        def _handle(self, method):
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            try:
                if method == "GET" and path in STATIC:
                    name, content_type = STATIC[path]
                    return self._send(200, (PUBLIC / name).read_bytes(), content_type)
                if method == "GET" and path == "/health":
                    return self._send(200, {"ok": True})
                if not self._authorised():
                    return self._send(401, {"error": "not authorised"})
                if method == "GET":
                    return self._get(path, query)
                self._post(path)
            except NotFound as e:
                self._send(404, {"error": str(e)})
            except Conflict as e:
                self._send(409, {"error": str(e)})
            except TooMany as e:
                self._send(429, {"error": str(e)})
            except ValueError as e:
                self._send(400, {"error": str(e)})
            except Exception:
                self.log_error("unhandled error on %s", path)
                traceback.print_exc()
                self._send(500, {"error": "internal error"})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            # Read the body before any reply. Closing a socket with unread data
            # resets the connection on Linux, and the client never sees the error.
            try:
                length = max(int(self.headers.get("Content-Length") or 0), 0)
            except ValueError:
                length = 0
            body = self.rfile.read(min(length, DRAIN_LIMIT))
            self.raw = body if length <= MAX_BODY else b""
            self._handle("POST")

    return Handler


def make_server(service: Service, settings: Settings, host="127.0.0.1", port=8000) -> ThreadingHTTPServer:
    if host not in LOCAL and not (settings.token or settings.demo):
        raise ValueError("Set OPSPILOT_TOKEN before listening on a non-local address")
    return ThreadingHTTPServer((host, port), make_handler(service, settings))
