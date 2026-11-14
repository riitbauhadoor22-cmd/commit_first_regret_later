# config.py — app-wide settings read from environment variables (backend/.env locally, Render's dashboard in production).
# APP_ENV (or ENV) = "production" | "development" (default). Production = Secure cookies, HSTS, no /docs.
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # does nothing when there is no .env (e.g. on Render)


# ===== SETTINGS =====
def app_env():
    """ "production" or "development". Read each time, so tests can switch it with monkeypatch."""
    value = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()
    return "production" if value in ("production", "prod") else "development"


def is_production():
    return app_env() == "production"


def docs_settings():
    """FastAPI options: the /docs, /redoc and /openapi.json pages only exist in development."""
    if is_production():
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


def log_app_mode():
    """Called once at startup: "App mode: production" in the server log."""
    logging.getLogger("uvicorn.error").info("App mode: %s", app_env())
