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

        -- ===== MONEY TABLES (every row belongs to one user) =====
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            type TEXT NOT NULL,                      -- Salary, Allowance, Side hustle, Scholarship, Other
            amount REAL NOT NULL,
            frequency TEXT NOT NULL,                 -- monthly, weekly, one-off
            date TEXT NOT NULL                       -- YYYY-MM-DD: start date, or date received (one-off)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            kind TEXT NOT NULL,                      -- need or want
            note TEXT NOT NULL DEFAULT '',
            date TEXT NOT NULL,                      -- YYYY-MM-DD (fixed bill: first month it counts)
            is_fixed INTEGER NOT NULL DEFAULT 0,     -- 1 = repeats every month
            source TEXT NOT NULL DEFAULT 'typed'     -- typed, voice, quick
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            category TEXT NOT NULL,
            monthly_limit REAL NOT NULL,
            UNIQUE (user_id, category)               -- one budget per category
        );
        CREATE TABLE IF NOT EXISTS savings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            bank_balance REAL NOT NULL DEFAULT 0,
            monthly_target REAL,                     -- empty = use 20% of regular income
            safety_net_saved REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            saved_amount REAL NOT NULL DEFAULT 0,
            deadline TEXT NOT NULL,                  -- YYYY-MM-DD
            priority INTEGER NOT NULL DEFAULT 2      -- 1 High, 2 Medium, 3 Low
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            goal_id INTEGER REFERENCES goals(id),    -- empty = safety net
            amount REAL NOT NULL,
            date TEXT NOT NULL
        );
        """)


def rows_to_dicts(rows):
    """Turn database rows into normal Python dicts (so they can be sent as JSON)."""
    return [dict(row) for row in rows]


def get_user_rows(db, table, user_id):
    """All rows of one money table that belong to this user. `table` is always a fixed name from our code."""
    return rows_to_dicts(db.execute(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY id", (user_id,)).fetchall())


def get_savings_row(db, user_id):
    """The user's savings row; makes an empty one the first time."""
    db.execute("INSERT OR IGNORE INTO savings (user_id) VALUES (?)", (user_id,))
    return dict(db.execute("SELECT * FROM savings WHERE user_id = ?", (user_id,)).fetchone())
