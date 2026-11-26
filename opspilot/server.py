"""JSON API and review dashboard (standard library HTTP server)."""
import hmac
import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .service import Service
from .store import Conflict, NotFound

DASHBOARD = Path(__file__).parent / "web" / "index.html"
LOCAL = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 32_000
DRAIN_LIMIT = 1_000_000


def make_server(service: Service, settings: Settings, host="127.0.0.1", port=8000) -> ThreadingHTTPServer:
    if host not in LOCAL and not settings.token:
        raise ValueError("Set OPSPILOT_TOKEN before listening on a non-local address")

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
            # Without a token, only answer to local host names (blocks DNS rebinding).
            name = urlparse("//" + self.headers.get("Host", "")).hostname
            return name in LOCAL

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

        def _handle(self, method):
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            try:
                if method == "GET" and path == "/":
                    return self._send(200, DASHBOARD.read_bytes(), "text/html")
                if method == "GET" and path == "/health":
                    return self._send(200, {"ok": True})
                if not self._authorised():
                    return self._send(401, {"error": "not authorised"})
                ticket = re.fullmatch(r"/api/tickets/(\d{1,12})(/decision)?", path)
                if method == "GET":
                    if path == "/api/tickets":
                        return self._send(200, service.store.list_tickets(query.get("status", [None])[0]))
                    if path == "/api/stats":
                        return self._send(200, service.store.stats())
                    if path == "/api/outbox":
                        return self._send(200, service.store.outbox())
                    if path == "/api/search":
                        return self._send(200, service.search(query.get("q", [""])[0]))
                    if ticket and not ticket.group(2):
                        return self._send(200, service.store.get(int(ticket.group(1))))
                if method == "POST" and path == "/api/messages":
                    data = self._body()
                    return self._send(201, service.submit(
                        data.get("message"), data.get("sender", "unknown"),
                        data.get("channel", "web"), data.get("external_id")))
                if method == "POST" and ticket and ticket.group(2):
                    data = self._body()
                    return self._send(200, service.store.decide(
                        int(ticket.group(1)), data.get("decision"), data.get("reviewer"), data.get("reply")))
                self._send(404, {"error": "not found"})
            except NotFound as e:
                self._send(404, {"error": str(e)})
            except Conflict as e:
                self._send(409, {"error": str(e)})
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

    return ThreadingHTTPServer((host, port), Handler)
