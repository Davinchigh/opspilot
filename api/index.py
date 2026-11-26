"""Entry point for Vercel: the same handler as the local server, in public demo mode."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OPSPILOT_DEMO"] = "1"
# Visitors must never be able to spend a model quota.
os.environ["OPSPILOT_PROVIDER"] = "offline"

from opspilot.config import Settings  # noqa: E402
from opspilot.server import make_handler  # noqa: E402
from opspilot.service import Service  # noqa: E402

settings = Settings.from_env()
if not settings.database_url:
    raise RuntimeError("DATABASE_URL is required when hosted")
handler = make_handler(Service(settings), settings)
