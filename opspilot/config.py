"""Settings come from environment variables, optionally loaded from a local .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    provider: str = "offline"  # "offline" or "openai" (any OpenAI-compatible API)
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    price_in: float = 0.0  # USD per 1M input tokens
    price_out: float = 0.0  # USD per 1M output tokens
    db_path: str = str(ROOT / "opspilot-v2.db")
    knowledge_dir: str = str(ROOT / "knowledge")
    token: str = ""  # required when the server is not bound to localhost
    database_url: str = ""  # Postgres, for hosting; empty means SQLite
    demo: bool = False  # public demo: no token, a private workspace per visitor
    max_tickets: int = 0  # per workspace; 0 means no limit
    max_total: int = 0  # all workspaces together; 0 means no limit
    rate_per_minute: int = 0  # write requests per address; 0 means no limit
    ttl_hours: int = 0  # delete tickets older than this; 0 means keep

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        env, d = os.environ.get, cls()
        demo = env("OPSPILOT_DEMO") == "1"

        def number(key, if_demo):
            return int(env(key) or (if_demo if demo else 0))

        return cls(
            provider=env("OPSPILOT_PROVIDER") or d.provider,
            base_url=env("OPSPILOT_BASE_URL", ""),
            api_key=env("OPSPILOT_API_KEY", ""),
            model=env("OPSPILOT_MODEL", ""),
            price_in=float(env("OPSPILOT_PRICE_IN") or 0),
            price_out=float(env("OPSPILOT_PRICE_OUT") or 0),
            db_path=env("OPSPILOT_DB") or d.db_path,
            knowledge_dir=env("OPSPILOT_KNOWLEDGE") or d.knowledge_dir,
            token=env("OPSPILOT_TOKEN", ""),
            # DATABASE_URL is a common name, so it is only used when asked for.
            database_url=env("DATABASE_URL", "") if demo or env("OPSPILOT_USE_DATABASE_URL") == "1" else "",
            demo=demo,
            max_tickets=number("OPSPILOT_MAX_TICKETS", 60),
            max_total=number("OPSPILOT_MAX_TOTAL", 5000),
            rate_per_minute=number("OPSPILOT_RATE_PER_MINUTE", 40),
            ttl_hours=number("OPSPILOT_TTL_HOURS", 24),
        )
