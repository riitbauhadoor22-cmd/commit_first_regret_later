# routes/income.py — /api/income: list, add, edit and delete the user's income.
# Regular income (monthly / weekly) is saved once and counted in every month from its start date.
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from categories import INCOME_TYPES
from errors import AppError
from database import find_user_row, get_user_rows, open_db
from models import Income, IncomeForm
from money import get_income_per_month, get_this_month, is_income_in_month, to_cents, to_money
from routes.auth import require_user
from routes.summary import MONTH_PATTERN

router = APIRouter(prefix="/api/income")


# ===== HELPERS =====
def find_income(db, income_id, user_id):
    """One income row of this user, or a 404 error (also when it belongs to someone else)."""
    row = find_user_row(db, Income, income_id, user_id)
    if row is None:
        raise AppError(404, "INCOME_NOT_FOUND", "Income not found.")
    return row


def form_to_values(form):
    """The column values to save ("type" from the form is saved in the "source" column)."""
    return {"name": form.name.strip(), "source": form.type, "amount_cents": to_cents(form.amount),
            "frequency": form.frequency, "date": form.date}


# ===== ROUTES =====
@router.get("")
def list_income(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                user_id: uuid.UUID = Depends(require_user)):
    """Regular income that counts this month, one-offs received this month, and the income types (for the form)."""
    month = month or get_this_month()
    with open_db() as db:
        incomes = get_user_rows(db, Income, user_id)
    regular, one_off = [], []
    for income in incomes:
        if not is_income_in_month(income, month):
            continue
        income["per_month"] = to_money(get_income_per_month(income))
        if income["frequency"] == "one-off":
            one_off.append(income)
        else:
            regular.append(income)
    return {"month": month, "regular": regular, "one_off": one_off, "types": INCOME_TYPES}


@router.post("", status_code=201)
def add_income(form: IncomeForm, user_id: uuid.UUID = Depends(require_user)):
    if not form.name.strip():
        raise AppError(400, "INCOME_NAME_REQUIRED", "Please give the income a name.")
    with open_db() as db:
        income = Income(user_id=user_id, **form_to_values(form))
        db.add(income)
        db.flush()  # fills in id and created_at
        return income.to_dict()


@router.put("/{income_id}")
def edit_income(income_id: uuid.UUID, form: IncomeForm, user_id: uuid.UUID = Depends(require_user)):
    if not form.name.strip():
        raise AppError(400, "INCOME_NAME_REQUIRED", "Please give the income a name.")
    with open_db() as db:
        income = find_income(db, income_id, user_id)
        for column, value in form_to_values(form).items():
            setattr(income, column, value)
        db.flush()
        return income.to_dict()


@router.delete("/{income_id}")
def delete_income(income_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        db.delete(find_income(db, income_id, user_id))
    return {"message": "Income deleted.", "code": "INCOME_DELETED"}
