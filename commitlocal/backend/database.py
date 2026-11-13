# database.py — connects to the database with SQLAlchemy and gives the routes a session to use.
# DATABASE_URL in .env picks the database: SQLite for development (default), PostgreSQL in production
# (Supabase / Neon). Tables are created and changed by Alembic migrations (backend/migrations/).
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from models import SavingsSettings

BACKEND_DIR = Path(__file__).parent
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_URL = "sqlite:///./app.db"

# ===== CONNECTION =====
engine = None
SessionLocal = None


def fix_url(url):
    """Make a DATABASE_URL ready for SQLAlchemy."""
    for prefix in ("postgres://", "postgresql://"):  # Supabase / Neon give these; use the psycopg driver
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    if url.startswith("sqlite:///./"):  # relative SQLite file -> always inside the backend folder
        return "sqlite:///" + (BACKEND_DIR / url[len("sqlite:///./"):]).as_posix()
    return url


def connect(url=None):
    """Open the database. Tests call this with a temporary SQLite file."""
    global engine, SessionLocal
    engine = create_engine(fix_url(url or os.getenv("DATABASE_URL") or DEFAULT_URL), pool_pre_ping=True)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def turn_on_sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys (and ON DELETE CASCADE) unless this is switched on for each connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


connect()


@contextmanager
def open_db():
    """Use as: `with open_db() as db:` — saves changes at the end, undoes them on an error, always closes."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables():
    """Bring the database up to the newest table layout (runs `alembic upgrade head`)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["engine"] = engine  # use the app's connection (tests: the temporary database)
    command.upgrade(config, "head")


# ===== SAFE QUERIES (always filtered by the logged-in user) =====
def get_user_rows(db, table, user_id):
    """All rows of one money table that belong to this user, oldest first, as dicts for JSON."""
    query = select(table).where(table.user_id == user_id)  # ORM query = parameterized SQL
    if hasattr(table, "created_at"):
        query = query.order_by(table.created_at)
    return [row.to_dict() for row in db.scalars(query)]


def find_user_row(db, table, row_id, user_id):
    """One row by id, but only if it belongs to this user (None otherwise)."""
    return db.scalar(select(table).where(table.id == row_id, table.user_id == user_id))


def get_savings_row(db, user_id):
    """The user's savings settings row; makes an empty one the first time."""
    row = db.scalar(select(SavingsSettings).where(SavingsSettings.user_id == user_id))
    if row is None:
        row = SavingsSettings(user_id=user_id, bank_balance_cents=0, safety_net_saved_cents=0)
        db.add(row)
        db.flush()  # write it now so later queries in this session can see it
    return row
