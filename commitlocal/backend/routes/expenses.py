# routes/expenses.py — /api/expenses: list, add, edit and delete expenses, plus the "Quick add" chips.
# A fixed bill (is_fixed = 1) is saved once and counted in every month from its date onwards.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from categories import get_default_kind
from database import get_user_rows, open_db
from models import ExpenseForm, QuickAddForm
from money import (get_everyday_expenses, get_fixed_bills, get_quick_add, get_this_month,
                   get_today, to_money)
from routes.auth import require_user
from routes.summary import MONTH_PATTERN

router = APIRouter(prefix="/api/expenses")


# ===== HELPERS =====
def find_expense(db, expense_id, user_id):
    """One expense row of this user, or a 404 error."""
    row = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Expense not found.")
    return dict(row)


def form_to_values(form):
    """The values to save, filling in the defaults: kind from the category, date = today."""
    kind = form.kind or get_default_kind(form.category)
    day = form.date.isoformat() if form.date else get_today()
    return (to_money(form.amount), form.category, kind, form.note.strip(), day, int(form.is_fixed), form.source)


def save_expense(db, values, user_id):
    cursor = db.execute("INSERT INTO expenses (amount, category, kind, note, date, is_fixed, source, user_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values + (user_id,))
    return find_expense(db, cursor.lastrowid, user_id)


# ===== ROUTES =====
@router.get("")
def list_expenses(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                  user_id: int = Depends(require_user)):
    """Everyday expenses of the month (newest first) and the fixed bills that count this month."""
    month = month or get_this_month()
    with open_db() as db:
        expenses = get_user_rows(db, "expenses", user_id)
    everyday = sorted(get_everyday_expenses(expenses, month), key=lambda e: (e["date"], e["id"]), reverse=True)
    return {"month": month, "everyday": everyday, "fixed": get_fixed_bills(expenses, month)}


@router.post("", status_code=201)
def add_expense(form: ExpenseForm, user_id: int = Depends(require_user)):
    with open_db() as db:
        return save_expense(db, form_to_values(form), user_id)


@router.get("/quick")
def list_quick_add(user_id: int = Depends(require_user)):
    """The 4 most repeated expenses of the last 30 days."""
    with open_db() as db:
        expenses = get_user_rows(db, "expenses", user_id)
    return get_quick_add(expenses, get_today())


@router.post("/quick", status_code=201)
def add_quick_expense(form: QuickAddForm, user_id: int = Depends(require_user)):
    """One tap on a chip: save that expense again with today's date."""
    with open_db() as db:
        chips = get_quick_add(get_user_rows(db, "expenses", user_id), get_today())
        chip = next((c for c in chips
                     if c["note"].strip().lower() == form.note.strip().lower() and c["amount"] == form.amount), None)
        if chip is None:
            raise HTTPException(404, "That quick-add button isn't there any more. Please refresh.")
        values = (chip["amount"], chip["category"], chip["kind"], chip["note"], get_today(), 0, "quick")
        return save_expense(db, values, user_id)


@router.put("/{expense_id}")
def edit_expense(expense_id: int, form: ExpenseForm, user_id: int = Depends(require_user)):
    with open_db() as db:
        old = find_expense(db, expense_id, user_id)
        values = list(form_to_values(form))
        values[6] = old["source"]  # keep how it was first added
        db.execute("UPDATE expenses SET amount = ?, category = ?, kind = ?, note = ?, date = ?, is_fixed = ?, source = ? "
                   "WHERE id = ? AND user_id = ?", tuple(values) + (expense_id, user_id))
        return find_expense(db, expense_id, user_id)


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, user_id: int = Depends(require_user)):
    with open_db() as db:
        find_expense(db, expense_id, user_id)
        db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
    return {"message": "Expense deleted."}
