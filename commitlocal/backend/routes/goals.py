# routes/goals.py — /api/goals: list goals (with "needs per month" and On track / Needs more),
# add, edit and delete goals, and add money to a goal.
from fastapi import APIRouter, Depends, HTTPException

from database import get_savings_row, get_user_rows, open_db
from models import AddMoneyForm, GoalForm
from money import (get_amount_to_add, get_goal_statuses, get_goals_warning, get_monthly_target,
                   get_this_month, get_today, to_money)
from routes.auth import require_user

router = APIRouter(prefix="/api/goals")


# ===== HELPERS =====
def find_goal(db, goal_id, user_id):
    """One goal of this user, or a 404 error."""
    row = db.execute("SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Goal not found.")
    return dict(row)


def build_goals_info(db, user_id):
    """All goals with their status, how much they need together, and the warning (if any)."""
    savings = get_savings_row(db, user_id)
    incomes = get_user_rows(db, "income", user_id)
    target = get_monthly_target(savings["monthly_target"], incomes, get_this_month())
    goals = get_goal_statuses(get_user_rows(db, "goals", user_id), target, get_today())
    total_needed = to_money(sum(g["needs_per_month"] for g in goals))
    return {
        "goals": goals,
        "monthly_target": target,
        "total_needed": total_needed,
        "warning": get_goals_warning(total_needed, target),
    }


def check_goal_form(form):
    if not form.name.strip():
        raise HTTPException(400, "Please give the goal a name.")


# ===== ROUTES =====
@router.get("")
def list_goals(user_id: int = Depends(require_user)):
    with open_db() as db:
        return build_goals_info(db, user_id)


@router.post("", status_code=201)
def add_goal(form: GoalForm, user_id: int = Depends(require_user)):
    check_goal_form(form)
    with open_db() as db:
        db.execute("INSERT INTO goals (user_id, name, target_amount, deadline, priority) VALUES (?, ?, ?, ?, ?)",
                   (user_id, form.name.strip(), to_money(form.target_amount), form.deadline.isoformat(), form.priority))
        return build_goals_info(db, user_id)


@router.put("/{goal_id}")
def edit_goal(goal_id: int, form: GoalForm, user_id: int = Depends(require_user)):
    check_goal_form(form)
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        if form.target_amount < goal["saved_amount"]:
            raise HTTPException(400, f"The target can't be less than what you've already saved (Rs {goal['saved_amount']:,.0f}).")
        db.execute("UPDATE goals SET name = ?, target_amount = ?, deadline = ?, priority = ? WHERE id = ? AND user_id = ?",
                   (form.name.strip(), to_money(form.target_amount), form.deadline.isoformat(), form.priority,
                    goal_id, user_id))
        return build_goals_info(db, user_id)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, user_id: int = Depends(require_user)):
    """Deletes the goal and its deposits. The money stays in the bank balance."""
    with open_db() as db:
        find_goal(db, goal_id, user_id)
        db.execute("DELETE FROM deposits WHERE goal_id = ? AND user_id = ?", (goal_id, user_id))
        db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
        return build_goals_info(db, user_id)


@router.post("/{goal_id}/add-money")
def add_money_to_goal(goal_id: int, form: AddMoneyForm, user_id: int = Depends(require_user)):
    """Save a deposit, add it to the goal and to the bank balance. Never fills a goal past its target."""
    with open_db() as db:
        goal = find_goal(db, goal_id, user_id)
        amount = get_amount_to_add(form.amount, goal["target_amount"], goal["saved_amount"])
        if amount <= 0:
            raise HTTPException(400, "This goal is already complete.")
        get_savings_row(db, user_id)
        db.execute("INSERT INTO deposits (user_id, goal_id, amount, date) VALUES (?, ?, ?, ?)",
                   (user_id, goal_id, amount, get_today()))
        db.execute("UPDATE goals SET saved_amount = saved_amount + ? WHERE id = ?", (amount, goal_id))
        db.execute("UPDATE savings SET bank_balance = bank_balance + ? WHERE user_id = ?", (amount, user_id))
        info = build_goals_info(db, user_id)
    info["added"] = amount
    return info
