# routes/budgets.py — /api/budgets: see and set the monthly limit for each spending category.
# A budget applies to every month until it is changed. "/api/budget" (no s) is kept as an alias so
# old cached copies of the app that used the singular name don't get a 404.
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select

from database import get_user_rows, open_db
from models import Budget, BudgetForm
from money import to_cents
from routes.auth import require_user
from routes.summary import MONTH_PATTERN

router = APIRouter(prefix="/api")


# ===== ROUTES =====
@router.get("/budgets")
@router.get("/budget", include_in_schema=False)  # alias (see top of file)
def list_budgets(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                 user_id: uuid.UUID = Depends(require_user)):
    """The user's budgets. `month` is accepted but the same budgets apply to every month."""
    with open_db() as db:
        return get_user_rows(db, Budget, user_id)


@router.put("/budgets")
@router.put("/budget", include_in_schema=False)  # alias (see top of file)
def set_budget(form: BudgetForm, user_id: uuid.UUID = Depends(require_user)):
    """Set one category's monthly limit. An empty limit removes the budget."""
    with open_db() as db:
        if form.monthly_limit is None:
            db.execute(delete(Budget).where(Budget.user_id == user_id, Budget.category == form.category))
        else:
            budget = db.scalar(select(Budget).where(Budget.user_id == user_id, Budget.category == form.category))
            if budget is None:  # first budget for this category
                budget = Budget(user_id=user_id, category=form.category)
                db.add(budget)
            budget.amount_cents = to_cents(form.monthly_limit)
        db.flush()
        return get_user_rows(db, Budget, user_id)
