# routes/expenses.py — /api/expenses: list a month's expenses and add a new one (logged-in user only).
import datetime

from fastapi import APIRouter, HTTPException, Request

from categories import CATEGORIES
from database import open_db
from models import ExpenseForm
from routes.auth import require_user

router = APIRouter(prefix="/api/expenses")


# ===== HELPERS =====
def this_month():
    return datetime.date.today().strftime("%Y-%m")


def check_month(month):
    try:
        datetime.datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Month must look like 2026-11.")


# ===== ROUTES =====
@router.get("")
def list_expenses(request: Request, month: str | None = None):
    user = require_user(request)
    month = month or this_month()
    check_month(month)
    with open_db() as db:
        rows = db.execute("SELECT id, amount, category, kind, note, date FROM expenses "
                          "WHERE user_id = ? AND date LIKE ? ORDER BY date DESC, id DESC",
                          (user["id"], month + "-%")).fetchall()  # "2026-11-%" = any day in that month
    expenses = [dict(row) for row in rows]
    return {"month": month, "expenses": expenses, "total": round(sum(e["amount"] for e in expenses), 2)}


@router.post("", status_code=201)
def add_expense(form: ExpenseForm, request: Request):
    user = require_user(request)
    if form.category not in CATEGORIES:
        raise HTTPException(400, "Please pick a category from the list.")
    day = (form.date or datetime.date.today()).isoformat()
    with open_db() as db:
        cur = db.execute("INSERT INTO expenses (user_id, amount, category, kind, note, date) VALUES (?, ?, ?, ?, ?, ?)",
                         (user["id"], round(form.amount, 2), form.category, CATEGORIES[form.category],
                          form.note.strip(), day))
    return {"id": cur.lastrowid, "message": "Expense saved."}
