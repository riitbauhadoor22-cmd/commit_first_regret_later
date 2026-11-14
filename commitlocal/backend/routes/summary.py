# routes/summary.py — GET /api/summary: everything the Money tab needs for one month
# (income, spent, saved, left to spend, needs/wants/savings %, category rows, fixed bills, recent expenses).
# Information the user hasn't given is None (not 0); "info" says which (provided / none / missing).
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import get_user_rows, open_db
from models import Budget, Deposit, Expense, Income
from money import get_summary, get_this_month
from routes.auth import require_user
from routes.info import read_info_status

router = APIRouter(prefix="/api")

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM


@router.get("/summary")
def read_summary(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                 user_id: uuid.UUID = Depends(require_user)):
    month = month or get_this_month()
    with open_db() as db:
        incomes = get_user_rows(db, Income, user_id)
        expenses = get_user_rows(db, Expense, user_id)
        deposits = get_user_rows(db, Deposit, user_id)
        budgets = get_user_rows(db, Budget, user_id)
        info = read_info_status(db, user_id, month)  # missing income / expenses → None, never Rs 0
    return get_summary(incomes, expenses, deposits, budgets, month, info)
