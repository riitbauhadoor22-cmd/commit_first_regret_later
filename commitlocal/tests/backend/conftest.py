# conftest.py — shared pytest setup: a fresh temporary database per test, fake email sending, and login helpers.
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))  # so "import main", "import database" find the backend files
# Never touch the real database: anything opened before a test starts uses a throwaway in-memory one
os.environ["DATABASE_URL"] = "sqlite://"

import database  # noqa: E402
import security  # noqa: E402
from sqlalchemy import select  # noqa: E402

from models import OtpCode  # noqa: E402

security.BCRYPT_ROUNDS = 4  # fast hashing in tests (the real app uses 14)

PASSWORD = "Strong!Pass1"


# ===== FIXTURES =====
@pytest.fixture
def new_client(tmp_path):
    """Makes TestClients (one per "browser") that share one empty temporary SQLite database."""
    database.connect(f"sqlite:///{tmp_path.as_posix()}/test.db")
    database.create_tables()  # runs the Alembic migrations, so they are tested too
    import main
    from fastapi.testclient import TestClient
    yield lambda: TestClient(main.app)
    database.engine.dispose()  # close the file so the temp folder can be deleted


@pytest.fixture
def client(new_client):
    return new_client()


@pytest.fixture
def sent_codes(monkeypatch):
    """Replaces the real Gmail sender: codes are stored in this list instead of emailed."""
    import routes.auth
    codes = []
    monkeypatch.setattr(routes.auth, "send_otp_email", lambda email, code: codes.append(code))
    return codes


# ===== HELPERS =====
def register(client, email="asha@example.com"):
    res = client.post("/api/auth/register", json={"full_name": "Asha", "email": email,
                                                  "password": PASSWORD, "confirm_password": PASSWORD})
    assert res.status_code == 201


def log_in(client, sent_codes, email="asha@example.com"):
    """Register + password + emailed code, so `client` holds a session cookie."""
    register(client, email)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    res = client.post("/api/auth/verify-code", json={"email": email, "code": sent_codes[-1]})
    assert res.status_code == 200
    return client


def age_codes(seconds):
    """Pretend all codes were made `seconds` earlier (instead of really waiting)."""
    with database.open_db() as db:
        for code in db.scalars(select(OtpCode)):
            code.created_at -= timedelta(seconds=seconds)
            code.expires_at -= timedelta(seconds=seconds)


@pytest.fixture
def logged_in(client, sent_codes):
    """A client with a logged-in user (session cookie set)."""
    return log_in(client, sent_codes)
