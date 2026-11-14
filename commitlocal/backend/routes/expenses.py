# routes/expenses.py — /api/expenses: list, add, edit and delete expenses, plus the "Quick add" chips.
# A fixed bill (is_fixed = 1) is saved once and counted in every month from its date onwards.
# GET /suggest-category?text= guesses a category from the note (own history, then keywords; category_keywords.py).
import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from categories import CATEGORIES, get_default_kind
from category_keywords import CATEGORY_KEYWORDS, suggest_category
from errors import AppError
from database import find_user_row, get_user_rows, open_db
from models import Expense, ExpenseForm, QuickAddForm
from money import (get_everyday_expenses, get_fixed_bills, get_quick_add, get_this_month,
                   get_today, to_cents)
from routes.auth import require_user
from routes.summary import MONTH_PATTERN

router = APIRouter(prefix="/api/expenses")


# ===== HELPERS =====
def find_expense(db, expense_id, user_id):
    """One expense row of this user, or a 404 error (also when it belongs to someone else)."""
    row = find_user_row(db, Expense, expense_id, user_id)
    if row is None:
        raise AppError(404, "EXPENSE_NOT_FOUND", "Expense not found.")
    return row


def form_to_values(form):
    """The column values to save, filling in the defaults: kind from the category, date = today."""
    return {"amount_cents": to_cents(form.amount), "category": form.category,
            "kind": form.kind or get_default_kind(form.category), "description": form.note.strip(),
            "date": form.date or datetime.date.today(), "is_fixed": form.is_fixed}


def save_expense(db, values, user_id, source):
    expense = Expense(user_id=user_id, source=source, **values)
    db.add(expense)
    db.flush()  # fills in id and created_at
    return expense.to_dict()


# ===== ROUTES =====
@router.get("")
def list_expenses(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                  category: Optional[str] = Query(default=None),
                  user_id: uuid.UUID = Depends(require_user)):
    """Everyday expenses of the month (newest first) and the fixed bills that count this month.
    Optional `category` keeps only that category's expenses."""
    if category is not None and category not in CATEGORIES:
        raise AppError(422, "INVALID_CATEGORY", "Please pick one of the listed categories.")
    month = month or get_this_month()
    with open_db() as db:
        expenses = get_user_rows(db, Expense, user_id)
    if category is not None:
        expenses = [e for e in expenses if e["category"] == category]
    everyday = sorted(get_everyday_expenses(expenses, month), key=lambda e: (e["date"], e["created_at"]), reverse=True)
    return {"month": month, "everyday": everyday, "fixed": get_fixed_bills(expenses, month)}


@router.post("", status_code=201)
def add_expense(form: ExpenseForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return save_expense(db, form_to_values(form), user_id, form.source)


@router.get("/quick")
def list_quick_add(user_id: uuid.UUID = Depends(require_user)):
    """The 4 most repeated expenses of the last 30 days."""
    with open_db() as db:
        expenses = get_user_rows(db, Expense, user_id)
    return get_quick_add(expenses, get_today())


@router.post("/quick", status_code=201)
def add_quick_expense(form: QuickAddForm, user_id: uuid.UUID = Depends(require_user)):
    """One tap on a chip: save that expense again with today's date."""
    with open_db() as db:
        chips = get_quick_add(get_user_rows(db, Expense, user_id), get_today())
        chip = next((c for c in chips
                     if c["note"].strip().lower() == form.note.strip().lower() and c["amount"] == form.amount), None)
        if chip is None:
            raise AppError(404, "QUICK_ADD_GONE", "That quick-add button isn't there any more. Please refresh.")
        values = {"amount_cents": to_cents(chip["amount"]), "category": chip["category"], "kind": chip["kind"],
                  "description": chip["note"], "date": datetime.date.today(), "is_fixed": False}
        return save_expense(db, values, user_id, "quick")


@router.get("/suggest-category")
def read_category_suggestion(text: str = Query(default="", max_length=100), user_id: uuid.UUID = Depends(require_user)):
    """A guessed category for a note like "KFC 350" (nothing is saved). Only this user's history is used."""
    with open_db() as db:
        expenses = get_user_rows(db, Expense, user_id)
    return suggest_category(text, expenses)


@router.get("/category-keywords")
def read_category_keywords(user_id: uuid.UUID = Depends(require_user)):
    """The Mauritian keyword list, so the phone can keep a copy and guess offline too."""
    return {"keywords": CATEGORY_KEYWORDS}


@router.put("/{expense_id}")
def edit_expense(expense_id: uuid.UUID, form: ExpenseForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        expense = find_expense(db, expense_id, user_id)
        for column, value in form_to_values(form).items():  # "source" is kept: how it was first added
            setattr(expense, column, value)
        db.flush()
        return expense.to_dict()


@router.delete("/{expense_id}")
def delete_expense(expense_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        db.delete(find_expense(db, expense_id, user_id))
    return {"message": "Expense deleted.", "code": "EXPENSE_DELETED"}
