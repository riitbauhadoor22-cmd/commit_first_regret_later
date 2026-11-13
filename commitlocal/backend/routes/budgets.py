# routes/budgets.py — /api/budgets: see and set the monthly limit for each spending category.
from fastapi import APIRouter, Depends

from database import get_user_rows, open_db
from models import BudgetForm
from money import to_money
from routes.auth import require_user

router = APIRouter(prefix="/api/budgets")


@router.get("")
def list_budgets(user_id: int = Depends(require_user)):
    with open_db() as db:
        return get_user_rows(db, "budgets", user_id)


@router.put("")
def set_budget(form: BudgetForm, user_id: int = Depends(require_user)):
    """Set one category's monthly limit. An empty limit removes the budget."""
    with open_db() as db:
        if form.monthly_limit is None:
            db.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, form.category))
        else:
            db.execute("INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?) "
                       "ON CONFLICT (user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                       (user_id, form.category, to_money(form.monthly_limit)))
        return get_user_rows(db, "budgets", user_id)
