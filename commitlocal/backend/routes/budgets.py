# routes/budgets.py — /api/budget: one overall monthly budget for ALL expenses, plus how much is spent that month.
from fastapi import APIRouter, Request

from database import open_db
from models import BudgetForm
from routes.auth import require_user
from routes.expenses import check_month, this_month

router = APIRouter(prefix="/api/budget")


# ===== ROUTES =====
@router.get("")
def get_budget(request: Request, month: str | None = None):
    """Budget + spent that month. monthly_limit is null if the user hasn't set one."""
    user = require_user(request)
    month = month or this_month()
    check_month(month)
    with open_db() as db:
        row = db.execute("SELECT monthly_limit FROM overall_budget WHERE user_id = ?", (user["id"],)).fetchone()
        spent = db.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE user_id = ? AND date LIKE ?",
                           (user["id"], month + "-%")).fetchone()["s"]
    limit = row["monthly_limit"] if row else None
    over_by = spent - limit if limit and spent > limit else 0
    return {"month": month, "monthly_limit": limit, "spent": round(spent, 2), "over_by": round(over_by, 2)}


@router.put("")
def set_budget(form: BudgetForm, request: Request):
    user = require_user(request)
    with open_db() as db:
        # Add the budget, or replace the old one if the user already has one
        db.execute("INSERT INTO overall_budget (user_id, monthly_limit) VALUES (?, ?) "
                   "ON CONFLICT(user_id) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                   (user["id"], round(form.monthly_limit, 2)))
    return {"message": "Budget saved."}
