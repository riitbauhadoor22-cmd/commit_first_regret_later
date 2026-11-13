# routes/savings.py — /api/savings: money in the bank, the monthly saving target,
# this month's saving progress, the safety net, and adding money to the safety net.
from fastapi import APIRouter, Depends

from database import get_savings_row, get_user_rows, open_db
from models import AddMoneyForm, SavingsForm
from money import (get_bank_bar, get_monthly_target, get_regular_income, get_safety_net,
                   get_saved_in_month, get_this_month, get_today, to_money)
from routes.auth import require_user

router = APIRouter(prefix="/api/savings")


# ===== HELPERS =====
def build_savings_info(db, user_id):
    """Everything the Targets tab's top 3 cards need, worked out for this month."""
    month = get_this_month()
    savings = get_savings_row(db, user_id)
    incomes = get_user_rows(db, "income", user_id)
    expenses = get_user_rows(db, "expenses", user_id)
    deposits = get_user_rows(db, "deposits", user_id)
    goals = get_user_rows(db, "goals", user_id)
    return {
        "bank_balance": savings["bank_balance"],
        "monthly_target": get_monthly_target(savings["monthly_target"], incomes, month),
        "monthly_target_custom": savings["monthly_target"],  # empty = using the 20% default
        "default_target": get_monthly_target(None, incomes, month),
        "regular_income": get_regular_income(incomes, month),
        "saved_this_month": get_saved_in_month(deposits, month),
        "safety_net": get_safety_net(expenses, savings["safety_net_saved"], month),
        "bank_bar": get_bank_bar(savings["bank_balance"], savings["safety_net_saved"], goals),
    }


# ===== ROUTES =====
@router.get("")
def read_savings(user_id: int = Depends(require_user)):
    with open_db() as db:
        return build_savings_info(db, user_id)


@router.put("")
def update_savings(form: SavingsForm, user_id: int = Depends(require_user)):
    """Update the bank balance and the monthly target (empty target = go back to 20% of regular income)."""
    target = to_money(form.monthly_target) if form.monthly_target is not None else None
    with open_db() as db:
        get_savings_row(db, user_id)
        db.execute("UPDATE savings SET bank_balance = ?, monthly_target = ? WHERE user_id = ?",
                   (to_money(form.bank_balance), target, user_id))
        return build_savings_info(db, user_id)


@router.post("/safety-net/add-money")
def add_to_safety_net(form: AddMoneyForm, user_id: int = Depends(require_user)):
    """Save a deposit (with no goal) and add it to the safety net and to the bank balance."""
    amount = to_money(form.amount)
    with open_db() as db:
        get_savings_row(db, user_id)
        db.execute("INSERT INTO deposits (user_id, goal_id, amount, date) VALUES (?, NULL, ?, ?)",
                   (user_id, amount, get_today()))
        db.execute("UPDATE savings SET safety_net_saved = safety_net_saved + ?, bank_balance = bank_balance + ? "
                   "WHERE user_id = ?", (amount, amount, user_id))
        return build_savings_info(db, user_id)
