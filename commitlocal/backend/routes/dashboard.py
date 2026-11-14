# routes/dashboard.py — the Dashboard tab (the first tab after logging in).
#   GET /api/dashboard?today=YYYY-MM-DD → balance, spending + saving graphs, loan projection, recap, health score,
#                                         weekly budget + badges, savings jar. Plain maths (services/dashboard.py),
#                                         NEVER the AI. "today" = the phone's local date (weeks + months follow it).
#   PUT /api/dashboard/weekly-budget     → {amount (empty = remove), today}: the planned spending per week.
# Only the logged-in user's rows are read. New badges are saved once and never removed.
import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from database import find_savings_row, get_user_rows, open_db, read_savings_values
from models import (Budget, Deposit, EarnedBadge, Expense, Income, MyLoan, SavingsGoal, WeeklyBudget,
                    WeeklyBudgetForm, iso)
from routes.auth import require_user
from routes.info import get_choices
from services.dashboard import build_dashboard

router = APIRouter(prefix="/api/dashboard")

BADGE_ORDER = ["FIRST_WEEK", "BUDGET_KEEPER", "CONSISTENT_PLANNER", "SAVINGS_STREAK"]
MAX_DAYS_FROM_SERVER = 2  # the phone's date may differ from the server's by a time zone, not more


# ===== HELPERS =====
def pick_today(today):
    """The phone's local date if it is sensible (within 2 days of the server's), otherwise the server's date."""
    server_today = datetime.date.today()
    if today is None or abs((today - server_today).days) > MAX_DAYS_FROM_SERVER:
        return server_today
    return today


def read_records(db, user_id):
    savings_row = find_savings_row(db, user_id)
    return {"incomes": get_user_rows(db, Income, user_id), "expenses": get_user_rows(db, Expense, user_id),
            "deposits": get_user_rows(db, Deposit, user_id), "goals": get_user_rows(db, SavingsGoal, user_id),
            "loans": get_user_rows(db, MyLoan, user_id),
            "savings_row": savings_row.to_dict() if savings_row else None}


def find_weekly_budget(db, user_id):
    return db.scalar(select(WeeklyBudget).where(WeeklyBudget.user_id == user_id))


def read_badges(db, user_id):
    rows = db.scalars(select(EarnedBadge).where(EarnedBadge.user_id == user_id))
    badges = [{"code": row.code, "earned_on": iso(row.earned_on)} for row in rows]
    return sorted(badges, key=lambda badge: (badge["earned_on"], BADGE_ORDER.index(badge["code"])
                                             if badge["code"] in BADGE_ORDER else 99))


def build_reply(db, user_id, today):
    records = read_records(db, user_id)
    weekly_row = find_weekly_budget(db, user_id)
    earned = {badge["code"] for badge in read_badges(db, user_id)}
    data = build_dashboard(records, get_choices(db, user_id), read_savings_values(db, user_id),
                           get_user_rows(db, Budget, user_id), weekly_row.to_dict() if weekly_row else None,
                           earned, today)
    for code, day in data.pop("new_badges").items():  # saved once; the unique constraint stops duplicates
        db.add(EarnedBadge(user_id=user_id, code=code, earned_on=datetime.date.fromisoformat(day)))
    db.flush()
    badges = read_badges(db, user_id)
    data["badges"] = {"earned": badges, "all": BADGE_ORDER, "new": sorted(set(b["code"] for b in badges) - earned)}
    return data


# ===== ROUTES =====
@router.get("")
def read_dashboard(today: Optional[datetime.date] = Query(default=None), user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return build_reply(db, user_id, pick_today(today))


@router.put("/weekly-budget")
def set_weekly_budget(form: WeeklyBudgetForm, user_id: uuid.UUID = Depends(require_user)):
    """Set / change / remove the weekly budget. Changing the amount keeps the start date; earned badges stay."""
    today = pick_today(form.today)
    with open_db() as db:
        row = find_weekly_budget(db, user_id)
        if form.amount is None:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(WeeklyBudget(user_id=user_id, amount_cents=round(form.amount * 100), set_on=today))
        else:
            row.amount_cents = round(form.amount * 100)
        db.flush()
        return build_reply(db, user_id, today)
