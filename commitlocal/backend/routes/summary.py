# routes/summary.py — GET /api/summary: everything the Money tab needs for one month
# (income, out, saved, left to spend, 50/30/20 split from services/month_summary.py + category rows, fixed bills,
# recent expenses from money.get_month_lists).
# Information the user hasn't given is None (not 0); "info" says which (provided / none / missing).
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import get_user_rows, open_db, read_savings_values
from models import Budget, Expense, Income, MyLoan
from money import get_month_lists, get_this_month
from routes.auth import require_user
from routes.info import read_info_status
from services.month_summary import build_month_summary

router = APIRouter(prefix="/api")

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM


@router.get("/summary")
def read_summary(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                 user_id: uuid.UUID = Depends(require_user)):
    month = month or get_this_month()
    with open_db() as db:
        incomes = get_user_rows(db, Income, user_id)
        expenses = get_user_rows(db, Expense, user_id)
        budgets = get_user_rows(db, Budget, user_id)
        loans = get_user_rows(db, MyLoan, user_id)
        savings = read_savings_values(db, user_id)
        info = read_info_status(db, user_id, month)  # missing income / expenses → None, never Rs 0
    flows = build_month_summary(incomes, expenses, loans, savings, info, month)  # the ONE shared month maths
    return {**flows, **get_month_lists(expenses, budgets, month)}
