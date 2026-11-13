# routes/income.py — /api/income: list, add, edit and delete the user's income.
# Regular income (monthly / weekly) is saved once and counted in every month from its start date.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from categories import INCOME_TYPES
from database import get_user_rows, open_db
from models import IncomeForm
from money import get_income_per_month, get_this_month, is_income_in_month, to_money
from routes.auth import require_user
from routes.summary import MONTH_PATTERN

router = APIRouter(prefix="/api/income")


# ===== HELPERS =====
def find_income(db, income_id, user_id):
    """One income row of this user, or a 404 error."""
    row = db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (income_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Income not found.")
    return dict(row)


def form_to_values(form):
    return (form.name.strip(), form.type, to_money(form.amount), form.frequency, form.date.isoformat())


# ===== ROUTES =====
@router.get("")
def list_income(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                user_id: int = Depends(require_user)):
    """Regular income that counts this month, one-offs received this month, and the income types (for the form)."""
    month = month or get_this_month()
    with open_db() as db:
        incomes = get_user_rows(db, "income", user_id)
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
def add_income(form: IncomeForm, user_id: int = Depends(require_user)):
    if not form.name.strip():
        raise HTTPException(400, "Please give the income a name.")
    with open_db() as db:
        cursor = db.execute("INSERT INTO income (name, type, amount, frequency, date, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                            form_to_values(form) + (user_id,))
        return find_income(db, cursor.lastrowid, user_id)


@router.put("/{income_id}")
def edit_income(income_id: int, form: IncomeForm, user_id: int = Depends(require_user)):
    if not form.name.strip():
        raise HTTPException(400, "Please give the income a name.")
    with open_db() as db:
        find_income(db, income_id, user_id)
        db.execute("UPDATE income SET name = ?, type = ?, amount = ?, frequency = ?, date = ? WHERE id = ? AND user_id = ?",
                   form_to_values(form) + (income_id, user_id))
        return find_income(db, income_id, user_id)


@router.delete("/{income_id}")
def delete_income(income_id: int, user_id: int = Depends(require_user)):
    with open_db() as db:
        find_income(db, income_id, user_id)
        db.execute("DELETE FROM income WHERE id = ? AND user_id = ?", (income_id, user_id))
    return {"message": "Income deleted."}
