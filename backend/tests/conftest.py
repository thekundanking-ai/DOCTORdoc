import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_DSN = "postgresql+psycopg2://doctordoc:doctordoc@localhost:5432/postgres"
TEST_DB = "doctordoc_test"
TEST_DSN = f"postgresql+psycopg2://doctordoc:doctordoc@localhost:5432/{TEST_DB}"


def _ensure_test_db() -> None:
    engine = create_engine(ADMIN_DSN)
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": TEST_DB}).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    engine.dispose()


_ensure_test_db()

os.environ["DATABASE_URL"] = TEST_DSN
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DEBUG"] = "true"

# Keep tests hermetic: never use real provider keys even if present in the root .env.
os.environ["GNANI_API_KEY"] = ""
os.environ["MERCURY_API_KEY"] = ""
os.environ["SMTP_HOST"] = ""

# Lift in-process auth rate limits so tests can run many requests.
os.environ["RATE_LIMIT_LOGIN"] = "100000"
os.environ["RATE_LIMIT_REGISTER"] = "100000"

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, get_engine
from app.main import app
from app.models import Base


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE report_delivery, consultation_report, transcription, audio_attachment, consultation, "
                "patient, users, clinic RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
    return TestClient(app)
