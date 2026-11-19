# savings_entries.py — the ONE place that changes savings totals. An entry (deposits table) is money put into
# savings (deposit) or taken out (withdrawal) of one place: general savings, the safety net or a goal.
#   deposit    → bank balance + amount, and the safety net / goal + amount (if one was picked)
#   withdrawal → bank balance − amount, and the safety net / goal − amount
# apply_entry(..., sign=-1) undoes an entry, so editing = undo the old one + apply the new one, and deleting = undo.
# Totals can never go below 0, and a goal never above its target (400 with a clear code instead). Taking money out of
# general savings may only use the FREE money (total − goals − safety net): set-aside money comes out of its goal.
from sqlalchemy import func, select

from database import find_user_row, get_savings_row
from errors import AppError
from models import SavingsGoal
from money import to_rupees


def find_entry_goal(db, goal_id, user_id):
    goal = find_user_row(db, SavingsGoal, goal_id, user_id) if goal_id else None
    if goal is None:
        raise AppError(404, "GOAL_NOT_FOUND", "Goal not found.")
    return goal


def apply_entry(db, user_id, kind, place, goal_id, cents, sign=1):
    """Moves the totals for one entry (sign = -1 undoes it). Raises before anything is half-changed."""
    change = cents * (1 if kind == "deposit" else -1) * sign
    savings = get_savings_row(db, user_id)
    bank = (savings.bank_balance_cents or 0) + change
    if bank < 0:
        raise AppError(400, "NOT_ENOUGH_SAVINGS", "You can't take out more than your total savings.",
                       {"available": to_rupees(savings.bank_balance_cents or 0)})
    if place == "general" and change < 0:
        in_goals = db.scalar(select(func.coalesce(func.sum(SavingsGoal.saved_cents), 0))
                             .where(SavingsGoal.user_id == user_id))
        free = max((savings.bank_balance_cents or 0) - savings.safety_net_saved_cents - in_goals, 0)
        if -change > free:
            raise AppError(400, "SET_ASIDE_FOR_GOALS", "This money is set aside for your goals – take it out from "
                           "a goal instead.", {"available": to_rupees(free)})
    goal = find_entry_goal(db, goal_id, user_id) if place == "goal" else None
    if place == "safety_net" and savings.safety_net_saved_cents + change < 0:
        raise AppError(400, "NOT_ENOUGH_SAVINGS", "You can't take out more than your safety net holds.",
                       {"available": to_rupees(savings.safety_net_saved_cents)})
    if goal is not None:
        if goal.saved_cents + change < 0:
            raise AppError(400, "NOT_ENOUGH_SAVINGS", "You can't take out more than this goal holds.",
                           {"available": to_rupees(goal.saved_cents)})
        if goal.saved_cents + change > goal.target_cents:
            raise AppError(400, "MORE_THAN_GOAL_NEEDS", "That's more than this goal still needs.",
                           {"left": to_rupees(max(goal.target_cents - goal.saved_cents, 0))})
        goal.saved_cents += change
    if place == "safety_net":
        savings.safety_net_saved_cents += change
    savings.bank_balance_cents = bank
