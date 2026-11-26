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
    db_path: str = str(ROOT / "opspilot.db")
    knowledge_dir: str = str(ROOT / "knowledge")
    token: str = ""  # required when the server is not bound to localhost

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        env, d = os.environ.get, cls()
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
        )
