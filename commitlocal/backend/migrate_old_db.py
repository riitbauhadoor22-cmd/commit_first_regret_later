# migrate_old_db.py — ONE-TIME script: copies users and their money data from the old SQLite file
# (backend/finance.db, integer ids, money in rupees) into the new database (DATABASE_URL, UUID ids, cents).
# Safe to run twice: users whose email is already in the new database are skipped.
# Run from the backend folder:  venv\Scripts\python migrate_old_db.py  [path\to\old.db]
# Not copied: login codes and sessions (everyone just logs in again), and the unused old "overall_budget" table.
import sqlite3
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

import database
from models import (Budget, Deposit, Expense, Income, Profile, SavingsGoal, SavingsSettings, User, utc_now)
from money import to_cents

OLD_DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "finance.db"


# ===== HELPERS =====
def cents(rupees):
    """Old rupee amount -> cents (never negative, the new tables don't allow it)."""
    return max(to_cents(rupees or 0), 0)


def day(text):
    return date.fromisoformat(text)


def created(old_id):
    """Keeps the old order: rows that had a smaller id get an earlier created_at."""
    return utc_now() + timedelta(microseconds=old_id)


def rows(old, sql, *params):
    return old.execute(sql, params).fetchall()  # parameterized: values are never put into the SQL text


# ===== COPY ONE USER =====
def copy_user(old, db, row):
    user = User(email=row["email"].strip().lower(), password_hash=row["password_hash"],
                failed_attempts=row["failed_attempts"], is_locked=bool(row["is_locked"]),
                created_at=datetime.fromtimestamp(row["created_at"], UTC).replace(tzinfo=None))
    db.add(user)
    db.flush()  # gives the user its new UUID
    db.add(Profile(user_id=user.id, full_name=row["full_name"]))
    old_id = row["id"]

    for r in rows(old, "SELECT * FROM income WHERE user_id = ?", old_id):
        db.add(Income(user_id=user.id, name=r["name"], source=r["type"], amount_cents=cents(r["amount"]),
                      frequency=r["frequency"], date=day(r["date"]), created_at=created(r["id"])))
    for r in rows(old, "SELECT * FROM expenses WHERE user_id = ?", old_id):
        db.add(Expense(user_id=user.id, amount_cents=cents(r["amount"]), category=r["category"], kind=r["kind"],
                       description=r["note"] or "", date=day(r["date"]), is_fixed=bool(r["is_fixed"]),
                       source=r["source"], created_at=created(r["id"])))
    for r in rows(old, "SELECT * FROM budgets WHERE user_id = ?", old_id):
        db.add(Budget(user_id=user.id, category=r["category"], amount_cents=cents(r["monthly_limit"])))
    for r in rows(old, "SELECT * FROM savings WHERE user_id = ?", old_id):
        target = r["monthly_target"]
        db.add(SavingsSettings(user_id=user.id, bank_balance_cents=cents(r["bank_balance"]),
                               monthly_target_cents=cents(target) if target is not None else None,
                               safety_net_saved_cents=cents(r["safety_net_saved"])))

    new_goal_ids = {}  # old goal id -> new goal UUID (deposits point at goals)
    for r in rows(old, "SELECT * FROM goals WHERE user_id = ?", old_id):
        goal = SavingsGoal(user_id=user.id, name=r["name"], target_cents=cents(r["target_amount"]),
                           saved_cents=cents(r["saved_amount"]), deadline=day(r["deadline"]),
                           priority=r["priority"], created_at=created(r["id"]))
        db.add(goal)
        db.flush()
        new_goal_ids[r["id"]] = goal.id
    for r in rows(old, "SELECT * FROM deposits WHERE user_id = ?", old_id):
        db.add(Deposit(user_id=user.id, goal_id=new_goal_ids.get(r["goal_id"]), amount_cents=cents(r["amount"]),
                       date=day(r["date"]), created_at=created(r["id"])))


# ===== MAIN =====
def main():
    if not OLD_DB.exists():
        print("No old database found at", OLD_DB)
        return
    database.create_tables()  # make sure the new tables exist
    old = sqlite3.connect(f"file:{OLD_DB.as_posix()}?mode=ro", uri=True)  # read-only: the old file is never changed
    old.row_factory = sqlite3.Row
    copied = skipped = 0
    for row in rows(old, "SELECT * FROM users ORDER BY id"):
        with database.open_db() as db:  # one transaction per user: all of their data, or nothing
            if db.scalar(select(User.id).where(User.email == row["email"].strip().lower())):
                skipped += 1
                continue
            copy_user(old, db, row)
            copied += 1
    old.close()
    print(f"Done. Users copied: {copied}. Already there (skipped): {skipped}.")


if __name__ == "__main__":
    main()
