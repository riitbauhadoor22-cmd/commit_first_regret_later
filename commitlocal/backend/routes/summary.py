# routes/summary.py — GET /api/summary: everything the Money tab needs for one month
# (income, spent, saved, left to spend, needs/wants/savings %, category rows, fixed bills, recent expenses).
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import get_user_rows, open_db
from money import get_summary, get_this_month
from routes.auth import require_user

router = APIRouter(prefix="/api")

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM


@router.get("/summary")
def read_summary(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                 user_id: int = Depends(require_user)):
    with open_db() as db:
        incomes = get_user_rows(db, "income", user_id)
        expenses = get_user_rows(db, "expenses", user_id)
        deposits = get_user_rows(db, "deposits", user_id)
        budgets = get_user_rows(db, "budgets", user_id)
    return get_summary(incomes, expenses, deposits, budgets, month or get_this_month())
