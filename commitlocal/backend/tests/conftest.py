# tests/conftest.py — shared test setup: lets tests import the backend files, and gives API tests
# a fresh, empty test database and a fake logged-in user (so no real login or email is needed).
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))  # the backend folder

import database  # noqa: E402  (must come after the line above)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test browser that talks to the app, logged in as user 1, using a temporary database."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.create_tables()

    from main import app
    from routes.auth import require_user

    app.dependency_overrides[require_user] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()
