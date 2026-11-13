# database.py — opens the SQLite database file (finance.db) and creates the tables the app needs.
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "finance.db"


@contextmanager
def open_db():
    """Use as: `with open_db() as db:` — saves changes at the end and always closes the file."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us read rows like row["email"]
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_tables():
    with open_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,              -- always saved in lowercase
            password_hash TEXT NOT NULL,             -- bcrypt hash, never the real password
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            is_locked INTEGER NOT NULL DEFAULT 0,    -- 1 = locked after 3 wrong passwords
            created_at INTEGER NOT NULL              -- unix time (seconds)
        );
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            code_hash TEXT NOT NULL,                 -- SHA-256 of the 6-digit code
            expires_at INTEGER NOT NULL,             -- 5 minutes after it was made
            tries INTEGER NOT NULL DEFAULT 0,        -- wrong guesses so far
            used INTEGER NOT NULL DEFAULT 0,         -- 1 = used, replaced or too many wrong guesses
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,             -- SHA-256 of the cookie value
            user_id INTEGER NOT NULL REFERENCES users(id),
            expires_at INTEGER NOT NULL
        );
        """)
