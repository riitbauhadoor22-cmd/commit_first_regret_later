# routes/month_recap.py — the month-end recap: the first time the user opens the app in a new month, a card about
# LAST month (saved vs the monthly target, total savings now, money left over). Shown once per month
# (profiles.recap_seen_month); the numbers are always worked out from the data (shared month maths), never stored.
#   GET  /api/month-recap        → {show, month, saved, target, status, total_savings, left_over, move_amount}
#   POST /api/month-recap/seen   → marks last month's recap as seen (Not now / closed)
#   POST /api/month-recap/move   → "Move Rs X to savings?" Yes: a normal savings entry (this month's income) dated the
#                                  last day of last month, so it counts as last month's saving. X is worked out again
#                                  here (never taken from the browser); also marks the recap as seen.
import calendar
import datetime
import math
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from database import get_user_rows, open_db, read_savings_values
from errors import AppError
from models import Deposit, Expense, Income, MyLoan, Profile
from money import get_month_of, get_this_month
from routes.auth import require_user
from routes.info import read_info_status
from routes.savings import build_savings_info, save_entry
from services.financial_analysis import get_previous_month
from services.month_summary import build_month_summary

router = APIRouter(prefix="/api/month-recap")


# ===== HELPERS =====
def get_profile(db, user_id):
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)
    return profile


def had_activity(incomes, expenses, deposits, month):
    """Anything recorded by then (income from that month or before, an expense or a savings entry that month)?
    No → no recap to show (e.g. a brand-new account)."""
    if any(get_month_of(row["date"]) <= month for row in incomes if row.get("date")):
        return True
    return any(get_month_of(row["date"]) == month for row in (*expenses, *deposits) if row.get("date"))


def build_recap(db, user_id, month):
    """Last month's numbers from the shared month maths. left_over None = income or spending unknown (no line)."""
    incomes = get_user_rows(db, Income, user_id)
    expenses = get_user_rows(db, Expense, user_id)
    deposits = get_user_rows(db, Deposit, user_id)
    savings = read_savings_values(db, user_id)
    flows = build_month_summary(incomes, expenses, get_user_rows(db, MyLoan, user_id), savings,
                                read_info_status(db, user_id, month), month, deposits=deposits)
    left = flows["left_to_spend"]
    move = math.floor(left) if left is not None and left >= 1 else None  # whole rupees, only when something is left
    return {"month": month, "saved": flows["saved"], "target": flows["monthly_target"],
            "status": flows["savings_status"]["code"], "total_savings": savings["bank_balance"],
            "left_over": left, "move_amount": move, "active": had_activity(incomes, expenses, deposits, month)}


def last_day_of(month):
    year, number = (int(part) for part in month.split("-"))
    return datetime.date(year, number, calendar.monthrange(year, number)[1])


# ===== ROUTES =====
@router.get("")
def read_month_recap(user_id: uuid.UUID = Depends(require_user)):
    month = get_previous_month(get_this_month())
    with open_db() as db:
        recap = build_recap(db, user_id, month)
        seen = get_profile(db, user_id).recap_seen_month == month
    show = recap.pop("active") and not seen
    return {"show": show, **recap}


@router.post("/seen")
def mark_recap_seen(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        get_profile(db, user_id).recap_seen_month = get_previous_month(get_this_month())
    return {"message": "Recap seen.", "code": "RECAP_SEEN"}


@router.post("/move")
def move_left_over(user_id: uuid.UUID = Depends(require_user)):
    month = get_previous_month(get_this_month())
    with open_db() as db:
        amount = build_recap(db, user_id, month)["move_amount"]
        if not amount:
            raise AppError(400, "NOTHING_LEFT", "There's nothing left over from last month to move.")
        entry = save_entry(db, user_id, "deposit", amount, last_day_of(month), "general", None, "income")
        get_profile(db, user_id).recap_seen_month = month
        return {**build_savings_info(db, user_id), "entry": entry.to_dict(), "moved": amount}
