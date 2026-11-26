"""Minimal Model Context Protocol server over stdio (newline-delimited JSON-RPC 2.0).

Assistants can read the queue, search company documents and submit messages.
There is deliberately no approve tool: only a person can send a reply.
"""
import json
import sys

from . import __version__
from .config import Settings
from .service import Service
from .store import Conflict, NotFound

PROTOCOL = "2025-06-18"
TEXT = {"type": "string"}


def tool(name, description, properties, required=()):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": list(required)}}


TOOLS = [
    tool("submit_message", "Triage a customer message and create a ticket for human review.",
         {"message": TEXT, "sender": TEXT}, ["message"]),
    tool("list_open_tickets", "List tickets waiting for a human decision.", {}),
    tool("get_ticket", "Get one ticket with its draft, sources, flags and history.",
         {"ticket_id": {"type": "integer"}}, ["ticket_id"]),
    tool("search_knowledge", "Search the company documents.", {"query": TEXT}, ["query"]),
]


def call_tool(service: Service, name: str, args: dict):
    if name == "submit_message":
        return service.submit(args.get("message"), args.get("sender", "mcp"), "mcp")
    if name == "list_open_tickets":
        return [{"id": t["id"], "status": t["status"], "message": t["message"],
                 "flags": t["result"]["flags"]} for t in service.store.list_tickets("open")]
    if name == "get_ticket":
        if not isinstance(args.get("ticket_id"), int):
            raise ValueError("ticket_id must be an integer")
        return service.store.get(args["ticket_id"])
    if name == "search_knowledge":
        return service.search(args.get("query"))
    raise ValueError(f"unknown tool: {name}")


def handle(service: Service, request: dict) -> dict | None:
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    request_id, method = request.get("id"), request.get("method")
    params = request.get("params") or {}
    if request_id is None:
        return None  # notifications get no reply

    def ok(result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    if method == "initialize":
        return ok({"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "opspilot", "version": __version__}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        try:
            value = call_tool(service, params.get("name"), params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(value)}], "isError": False})
        except (ValueError, NotFound, Conflict) as e:
            return ok({"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:  # keep the server alive; details go to stderr
            print(f"tool error: {e!r}", file=sys.stderr)
            return ok({"content": [{"type": "text", "text": "internal error"}], "isError": True})
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}


def run(settings: Settings, stdin=None, stdout=None) -> None:
    if stdin is None:  # MCP is UTF-8; Windows consoles default to another encoding
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline='\n')
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    service = Service(settings)
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = handle(service, json.loads(line))
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if response:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
