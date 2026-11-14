# routes/savings.py — /api/savings: money in the bank, the monthly saving target,
# this month's saving progress, the safety net, and adding money to the safety net.
import datetime
import uuid

from fastapi import APIRouter, Depends

from database import get_savings_row, get_user_rows, open_db, read_savings_values
from models import AddMoneyForm, Deposit, Expense, Income, SavingsForm, SavingsGoal
from money import (get_bank_bar, get_monthly_target, get_regular_income, get_safety_net,
                   get_saved_in_month, get_this_month, to_cents)
from routes.auth import require_user
from routes.info import read_info_status

router = APIRouter(prefix="/api/savings")


# ===== HELPERS =====
def build_savings_info(db, user_id):
    """Everything the Targets tab's top 3 cards need, worked out for this month."""
    month = get_this_month()
    savings = read_savings_values(db, user_id)  # never creates a Rs 0 row just by looking
    incomes = get_user_rows(db, Income, user_id)
    expenses = get_user_rows(db, Expense, user_id)
    deposits = get_user_rows(db, Deposit, user_id)
    goals = get_user_rows(db, SavingsGoal, user_id)
    return {
        "info": read_info_status(db, user_id, month)["savings"],  # provided / none / missing
        "bank_balance": savings["bank_balance"],  # None = not added yet
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
    """Save a deposit (with no goal) and add it to the safety net and to the bank balance."""
    cents = to_cents(form.amount)
    with open_db() as db:
        savings = get_savings_row(db, user_id)
        db.add(Deposit(user_id=user_id, goal_id=None, amount_cents=cents, date=datetime.date.today()))
        savings.safety_net_saved_cents += cents
        if savings.bank_balance_cents is not None:  # no balance added yet → don't invent one
            savings.bank_balance_cents += cents
        db.flush()
        return build_savings_info(db, user_id)
