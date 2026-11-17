"""Runtime settings, all from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:5432/deliberation_partner"
    # Railway and Heroku hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _db_url()
SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-secret-change-me-before-deploying-0000"
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "lucy@example.org").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "change-me"
ADMIN_NAME_SET = bool((os.environ.get("ADMIN_NAME") or "").strip())
ADMIN_NAME = (os.environ.get("ADMIN_NAME") or "").strip() or "Organiser"
TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "72"))

MODELS_FILE = Path(os.environ.get("MODELS_FILE", ROOT / "configs" / "models.yaml"))
# Tags at or above this confidence go straight into the flow; the rest wait for the moderator.
TAG_AUTO_CONFIRM = float(os.environ.get("TAG_AUTO_CONFIRM", "0.75"))
# Evaluation size: conversations = EVAL_PERSONAS x EVAL_SCENARIOS, each EVAL_TURNS long.
EVAL_PERSONAS = [p for p in os.environ.get("EVAL_PERSONAS", "novice-trusting,novice-trusting-m,expert-skeptic,strong-advocate").split(",") if p]
EVAL_SCENARIOS = [s for s in os.environ.get("EVAL_SCENARIOS", "ask_bot_opinion,seek_validation,perspective_roleplay").split(",") if s]
EVAL_TURNS = int(os.environ.get("EVAL_TURNS", "3"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
STANDIN_DELAY_S = float(os.environ.get("STANDIN_DELAY_S", "3"))
