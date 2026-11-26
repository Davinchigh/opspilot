"""The one place that the web API, CLI and MCP server all call."""
from .config import Settings
from .pipeline import Pipeline
from .store import Conflict, Store

MAX_MESSAGE = 4000


class Service:
    def __init__(self, settings: Settings, pipeline: Pipeline | None = None):
        self.settings = settings
        self.pipeline = pipeline or Pipeline(settings)
        self.store = Store(settings.db_path, settings.database_url)

    def submit(self, message, sender="unknown", channel="web", external_id=None,
               workspace="local") -> dict:
        for name, value in (("message", message), ("sender", sender), ("channel", channel)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if len(message) > MAX_MESSAGE or len(sender) > 200 or len(channel) > 50:
            raise ValueError("input is too long")
        if external_id is not None:
            if not isinstance(external_id, str) or not 0 < len(external_id) <= 200:
                raise ValueError("external_id must be short non-empty text")
            existing = self.store.find_external(external_id, workspace)
            if existing:
                return existing
        self._make_room(workspace)
        result = self.pipeline.run(message.strip())
        return self.store.create(message.strip(), sender.strip(), channel.strip(), result,
                                 external_id, workspace)

    def _make_room(self, workspace: str) -> None:
        s = self.settings
        if s.ttl_hours:
            self.store.purge(s.ttl_hours)
        if s.max_tickets and self.store.count(workspace) >= s.max_tickets:
            raise Conflict(f"This workspace holds {s.max_tickets} messages. Reset it to add more.")
        if s.max_total and self.store.count() >= s.max_total:
            raise Conflict("The demo is full for today. Try again tomorrow.")

    def search(self, query: str) -> list[dict]:
        if not isinstance(query, str):
            raise ValueError("query must be text")
        return [{"id": c.id, "score": s, "text": c.text} for c, s in self.pipeline.index.search(query)]
