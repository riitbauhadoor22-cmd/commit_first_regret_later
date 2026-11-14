# routes/forecast.py — GET /api/forecast?today=YYYY-MM-DD&month=YYYY-MM: the spending forecast for this month
# ("you'll spend about Rs X, budget Rs Y, about Rs Z left on the last day") and a "ready by" month per goal.
# Plain maths in services/forecast.py on the logged-in user's own rows only; never the AI.
# "today" = the phone's local date (same rule as the Dashboard). Another month → spending "available": false.
import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import get_user_rows, open_db, read_savings_values
from models import Budget, Deposit, Expense, Income, MyLoan, SavingsGoal
from routes.auth import require_user
from routes.dashboard import pick_today
from routes.summary import MONTH_PATTERN
from routes.info import read_info_status
from services.forecast import build_goal_etas
from services.month_summary import build_month_summary

router = APIRouter(prefix="/api")


# ===== ROUTES =====
@router.get("/forecast")
def read_forecast(today: Optional[datetime.date] = Query(default=None),
                  month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                  user_id: uuid.UUID = Depends(require_user)):
    today = pick_today(today)
    with open_db() as db:
        incomes = get_user_rows(db, Income, user_id)
        expenses = get_user_rows(db, Expense, user_id)
        deposits = get_user_rows(db, Deposit, user_id)
        budgets = get_user_rows(db, Budget, user_id)
        goals = get_user_rows(db, SavingsGoal, user_id)
        loans = get_user_rows(db, MyLoan, user_id)
        savings = read_savings_values(db, user_id)
        info = read_info_status(db, user_id, month or today.isoformat()[:7])
    # Same shared maths as the Money card: left at month end = income − forecast spending − saved_this_month
    flows = build_month_summary(incomes, expenses, loans, savings, info, month or today.isoformat()[:7], today, budgets)
    return {"today": today.isoformat(),
            "spending": flows["forecast"],
            "goals": build_goal_etas(goals, deposits, today)}
