# routes/info.py — optional financial information ("Permission Denied" challenge).
#   GET /api/info-status?month=YYYY-MM → {"income", "expenses", "loans", "savings"}: provided / none / missing
#   PUT /api/info-choices {topic, month?, none} → mark a topic "I have none" (none: true) or undo it (none: false)
# read_info_status() is also used by the summary, savings, goals and insights routes.
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select

from database import find_savings_row, get_user_rows, open_db
from info_status import choice_month, get_info_status
from models import Deposit, Expense, Income, InfoChoice, InfoChoiceForm, MyLoan, SavingsGoal
from money import get_this_month
from routes.auth import require_user

router = APIRouter(prefix="/api")

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"  # YYYY-MM


# ===== HELPERS (used by other routes too) =====
def get_choices(db, user_id):
    """{(topic, month), …} the user marked as "I have none"."""
    rows = db.execute(select(InfoChoice.topic, InfoChoice.month).where(InfoChoice.user_id == user_id))
    return {(row.topic, row.month) for row in rows}


def read_info_status(db, user_id, month):
    savings_row = find_savings_row(db, user_id)
    return get_info_status(
        get_user_rows(db, Income, user_id), get_user_rows(db, Expense, user_id),
        get_user_rows(db, Deposit, user_id), get_user_rows(db, SavingsGoal, user_id),
        savings_row.to_dict() if savings_row else None, get_user_rows(db, MyLoan, user_id),
        get_choices(db, user_id), month)


# ===== ROUTES =====
@router.get("/info-status")
def read_status(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return read_info_status(db, user_id, month or get_this_month())


@router.put("/info-choices")
def set_info_choice(form: InfoChoiceForm, user_id: uuid.UUID = Depends(require_user)):
    """"I have none" for a topic, or undo it. Adding a real record later always wins over this choice."""
    month = form.month or get_this_month()
    stored_month = choice_month(form.topic, month)
    with open_db() as db:
        db.execute(delete(InfoChoice).where(InfoChoice.user_id == user_id, InfoChoice.topic == form.topic,
                                            InfoChoice.month == stored_month))
        if form.none:
            db.add(InfoChoice(user_id=user_id, topic=form.topic, month=stored_month))
        db.flush()
        return read_info_status(db, user_id, month)
