# routes/goals.py — /api/goals: list goals (with "needs per month" and On track / Needs more),
# add, edit and delete goals, and add money to a goal.
import datetime
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete

from errors import AppError
from database import find_user_row, get_user_rows, open_db, read_savings_values
from models import AddMoneyForm, Deposit, GoalForm, Income, SavingsGoal
from money import (get_amount_to_add, get_goal_statuses, get_goals_warning, get_monthly_target,
                   get_this_month, get_today, to_cents, to_money, to_rupees)
from routes.auth import require_user
from services.inflation import project_goal

router = APIRouter(prefix="/api/goals")


# ===== HELPERS =====
def find_goal(db, goal_id, user_id):
    """One goal of this user, or a 404 error (also when it belongs to someone else)."""
    row = find_user_row(db, SavingsGoal, goal_id, user_id)
    if row is None:
        raise AppError(404, "GOAL_NOT_FOUND", "Goal not found.")
    return row


def build_goals_info(db, user_id):
    """All goals with their status, how much they need together, and the warning (if any)."""
    savings = read_savings_values(db, user_id)
    incomes = get_user_rows(db, Income, user_id)
    target = get_monthly_target(savings["monthly_target"], incomes, get_this_month())
    goals = get_goal_statuses(get_user_rows(db, SavingsGoal, user_id), target, get_today())
    total_needed = to_money(sum(g["needs_per_month"] or 0 for g in goals))  # None = no plan, adds nothing
    return {
        "goals": goals,
        "monthly_target": target,
        "total_needed": total_needed,
        "warning": get_goals_warning(total_needed, target),
    }


def check_goal_form(form):
    if not form.name.strip():
        raise AppError(400, "GOAL_NAME_REQUIRED", "Please give the goal a name.")


# ===== ROUTES =====
@router.get("")
def list_goals(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return build_goals_info(db, user_id)


@router.post("", status_code=201)
def add_goal(form: GoalForm, user_id: uuid.UUID = Depends(require_user)):
    check_goal_form(form)
    with open_db() as db:
        db.add(SavingsGoal(user_id=user_id, name=form.name.strip(), target_cents=to_cents(form.target_amount),
                           saved_cents=0, deadline=form.deadline, priority=form.priority,
                           category=form.category))
        db.flush()
        return build_goals_info(db, user_id)


@router.put("/{goal_id}")
def edit_goal(goal_id: uuid.UUID, form: GoalForm, user_id: uuid.UUID = Depends(require_user)):
    check_goal_form(form)
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        if to_cents(form.target_amount) < goal.saved_cents:
            raise AppError(400, "TARGET_BELOW_SAVED",
                           f"The target can't be less than what you've already saved (Rs {to_rupees(goal.saved_cents):,.0f}).",
                           {"saved": to_rupees(goal.saved_cents)})
        goal.name, goal.target_cents = form.name.strip(), to_cents(form.target_amount)
        goal.deadline, goal.priority, goal.category = form.deadline, form.priority, form.category
        db.flush()
        return build_goals_info(db, user_id)


@router.delete("/{goal_id}")
def delete_goal(goal_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    """Deletes the goal and its deposits. The money stays in the bank balance."""
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        db.execute(delete(Deposit).where(Deposit.goal_id == goal.id, Deposit.user_id == user_id))  # (the database cascade does this too)
        db.delete(goal)
        db.flush()
        return build_goals_info(db, user_id)


@router.get("/{goal_id}/inflation-projection")
def goal_inflation_projection(goal_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    """Estimated cost of this goal at its deadline after inflation (Statistics Mauritius CPI). Estimate only."""
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        return project_goal(to_rupees(goal.target_cents), to_rupees(goal.saved_cents), goal.deadline, goal.category)


@router.post("/{goal_id}/add-money")
def add_money_to_goal(goal_id: uuid.UUID, form: AddMoneyForm, user_id: uuid.UUID = Depends(require_user)):
    """Save a deposit and add it to the goal. Never fills a goal past its target. The goal's money is set aside
    from the bank balance (not new money), so the bank balance itself does NOT change."""
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        amount = get_amount_to_add(form.amount, to_rupees(goal.target_cents), to_rupees(goal.saved_cents))
        if amount <= 0:
            raise AppError(400, "GOAL_COMPLETE", "This goal is already complete.")
        cents = to_cents(amount)
        db.add(Deposit(user_id=user_id, goal_id=goal.id, amount_cents=cents, date=datetime.date.today()))
        goal.saved_cents += cents
        db.flush()
        info = build_goals_info(db, user_id)
    info["added"] = amount
    return info
