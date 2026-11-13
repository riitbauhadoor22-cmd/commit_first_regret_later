# conftest.py — shared pytest setup: a fresh temporary database per test, fake email sending, and login helpers.
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))  # so "import main", "import database" find the backend files

import database  # noqa: E402
import security  # noqa: E402

security.BCRYPT_ROUNDS = 4  # fast hashing in tests (the real app uses 14)

PASSWORD = "Strong!Pass1"


# ===== FIXTURES =====
@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient using an empty temporary database (never the real finance.db)."""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    import main  # imported after DB_PATH is patched
    from fastapi.testclient import TestClient
    database.create_tables()
    return TestClient(main.app)


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


def age_codes(seconds):
    """Pretend all codes were made `seconds` earlier (instead of really waiting)."""
    with database.open_db() as db:
        db.execute("UPDATE otp_codes SET created_at = created_at - ?, expires_at = expires_at - ?",
                   (seconds, seconds))


@pytest.fixture
def logged_in(client, sent_codes):
    """A client with a logged-in user (session cookie set)."""
    register(client)
    client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    res = client.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": sent_codes[-1]})
    assert res.status_code == 200
    return client
