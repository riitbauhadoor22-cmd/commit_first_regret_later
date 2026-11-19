# routes/savings.py — /api/savings: total savings (bank balance), the monthly saving target, this month's REAL
# saving, the safety net, and the savings entries:
#   GET    /api/savings/entries?month=   → this month's "Add to savings" / "Take out" entries (newest first)
#   POST   /api/savings/entries          → {kind deposit/withdrawal, amount, date, place general/safety_net/goal,
#                                            goal_id} — moves the totals (savings_entries.py)
#   PUT    /api/savings/entries/{id}     → edit (the old entry's effect is undone first)
#   DELETE /api/savings/entries/{id}     → delete (its effect is undone)
# "Update total savings" (PUT /api/savings) only sets the starting balance: it is never "saved this month".
import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import find_user_row, get_savings_row, get_user_rows, open_db, read_savings_values
from errors import AppError
from models import AddMoneyForm, Deposit, Expense, Income, MyLoan, SavingsEntryForm, SavingsForm, SavingsGoal
from money import (get_bank_bar, get_month_of, get_monthly_target, get_regular_income, get_safety_net, get_this_month,
                   to_cents)
from routes.auth import require_user
from routes.summary import MONTH_PATTERN
from savings_entries import apply_entry
from routes.info import read_info_status
from services.month_summary import build_month_summary, get_saving_progress

router = APIRouter(prefix="/api/savings")


# ===== HELPERS =====
def build_savings_info(db, user_id):
    """Everything the Targets tab's top 3 cards need, worked out for this month."""
    month = get_this_month()
    savings = read_savings_values(db, user_id)  # never creates a Rs 0 row just by looking
    incomes = get_user_rows(db, Income, user_id)
    expenses = get_user_rows(db, Expense, user_id)
    goals = get_user_rows(db, SavingsGoal, user_id)
    info = read_info_status(db, user_id, month)
    flows = build_month_summary(incomes, expenses, get_user_rows(db, MyLoan, user_id), savings, info, month,
                                deposits=get_user_rows(db, Deposit, user_id))
    return {
        "info": info["savings"],  # provided / none / missing
        "bank_balance": savings["bank_balance"],  # bank_savings_balance; None = not added yet
        "monthly_target": flows["monthly_target"],
        "monthly_target_custom": savings["monthly_target"],  # empty = using the 20% default
        "default_target": get_monthly_target(None, incomes, month),
        "regular_income": get_regular_income(incomes, month),
        "saved_this_month": flows["saved"],  # same number as "Saved" on the Money card
        "saving_progress": get_saving_progress(flows["saved"], flows["monthly_target"]),
        "safety_net": get_safety_net(expenses, savings["safety_net_saved"], month),
        "bank_bar": get_bank_bar(savings["bank_balance"], savings["safety_net_saved"], goals),
    }


# ===== ROUTES =====
@router.get("")
def read_savings(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return build_savings_info(db, user_id)


@router.put("")
def update_savings(form: SavingsForm, user_id: uuid.UUID = Depends(require_user)):
    """Update the bank balance and the monthly target (empty target = go back to 20% of regular income)."""
    with open_db() as db:
        savings = get_savings_row(db, user_id)
        savings.bank_balance_cents = to_cents(form.bank_balance) if form.bank_balance is not None else None
        savings.monthly_target_cents = to_cents(form.monthly_target) if form.monthly_target is not None else None
        db.flush()
        return build_savings_info(db, user_id)


@router.post("/safety-net/add-money")
def add_to_safety_net(form: AddMoneyForm, user_id: uuid.UUID = Depends(require_user)):
    """Older shortcut: a deposit into the safety net today (same as POST /entries)."""
    with open_db() as db:
        save_entry(db, user_id, "deposit", form.amount, datetime.date.today(), "safety_net", None)
        return build_savings_info(db, user_id)


# ===== SAVINGS ENTRIES =====
def save_entry(db, user_id, kind, amount, day, place, goal_id):
    cents = to_cents(amount)
    goal_id = goal_id if place == "goal" else None
    if place == "goal" and goal_id is None:
        raise AppError(400, "GOAL_REQUIRED", "Pick the goal this money is for.")
    apply_entry(db, user_id, kind, place, goal_id, cents)
    entry = Deposit(user_id=user_id, kind=kind, place=place, goal_id=goal_id, amount_cents=cents, date=day)
    db.add(entry)
    db.flush()
    return entry


def find_entry(db, entry_id, user_id):
    row = find_user_row(db, Deposit, entry_id, user_id)
    if row is None:
        raise AppError(404, "ENTRY_NOT_FOUND", "Savings entry not found.")
    return row


def undo_entry(db, user_id, entry):
    apply_entry(db, user_id, entry.kind, entry.place, entry.goal_id, entry.amount_cents, sign=-1)


@router.get("/entries")
def list_entries(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                 user_id: uuid.UUID = Depends(require_user)):
    month = month or get_this_month()
    with open_db() as db:
        rows = [d for d in get_user_rows(db, Deposit, user_id) if get_month_of(d["date"]) == month]
    return {"month": month, "entries": sorted(rows, key=lambda d: (d["date"], d["created_at"]), reverse=True)}


@router.post("/entries", status_code=201)
def add_entry(form: SavingsEntryForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        entry = save_entry(db, user_id, form.kind, form.amount, form.date or datetime.date.today(), form.place,
                           form.goal_id)
        return {**build_savings_info(db, user_id), "entry": entry.to_dict()}


@router.put("/entries/{entry_id}")
def edit_entry(entry_id: uuid.UUID, form: SavingsEntryForm, user_id: uuid.UUID = Depends(require_user)):
    """Undo the old entry's effect, then apply the new values (all or nothing)."""
    with open_db() as db:
        old = find_entry(db, entry_id, user_id)
        day = form.date or old.date
        undo_entry(db, user_id, old)
        db.delete(old)
        db.flush()
        entry = save_entry(db, user_id, form.kind, form.amount, day, form.place, form.goal_id)
        return {**build_savings_info(db, user_id), "entry": entry.to_dict()}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        entry = find_entry(db, entry_id, user_id)
        undo_entry(db, user_id, entry)
        db.delete(entry)
        db.flush()
        return build_savings_info(db, user_id)
