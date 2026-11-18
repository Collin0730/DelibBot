"""Tests run against a real Postgres database named by TEST_DATABASE_URL, with the offline mock models."""
import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/delib_test")
os.environ["ADMIN_EMAIL"] = "lucy@example.org"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["STANDIN_DELAY_S"] = "0"
os.environ["EVAL_PERSONAS"] = "novice-trusting,novice-trusting-m"
os.environ["EVAL_SCENARIOS"] = "ask_bot_opinion"
os.environ["EVAL_TURNS"] = "2"
for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(key, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app import models
    from app.db import Base, engine
    from app.main import app

    with engine.begin() as conn:
        conn.execute(text(models.DROP_VIEWS_SQL))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        conn.execute(text(models.VIEWS_SQL))
    with TestClient(app) as c:
        yield c
