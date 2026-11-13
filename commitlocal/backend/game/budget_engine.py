# game/budget_engine.py — checks a Budget Challenge allocation and adds it up. Works in whole cents (no float drift).
from errors import AppError
from game.events import event_changes
from game.scenarios import minimum_of
from money import to_cents, to_rupees


# ===== CHECKS =====
def clean_allocation(level, allocation):
    """{category: rupees} -> {category: cents} for every category of the level (missing = 0).
    Only this level's categories; locked commitments must keep their config value."""
    ids = {category["id"] for category in level["categories"]}
    if any(key not in ids for key in allocation):
        raise AppError(400, "GAME_UNKNOWN_CATEGORY", "That category isn't part of this level.")
    cents = {category["id"]: to_cents(allocation.get(category["id"], 0)) for category in level["categories"]}
    for category in level["categories"]:
        if "locked" in category and cents[category["id"]] != to_cents(category["locked"]):
            raise AppError(400, "GAME_LOCKED_CHANGED", "Fixed commitments can't be changed.")
    return cents


def check_within_income(level, cents, event):
    """Over-income budgets are blocked (the player must fix them before submitting)."""
    income = effective_income(level, event)
    if sum(cents.values()) > income:
        over = to_rupees(sum(cents.values()) - income)
        raise AppError(400, "GAME_OVER_INCOME", f"Your budget is Rs {over:,.0f} over your income.", {"over": over})


# ===== TOTALS =====
def effective_income(level, event):
    """Income in cents, + a bonus event."""
    return to_cents(level["income"]) + event_changes(event)[0]


def minimums(level, event):
    """{category: cents it needs} for essential categories, after a cost / discount event (never below 0)."""
    changes = event_changes(event)[1]
    needed = {}
    for category in level["categories"]:
        base = to_cents(minimum_of(category))
        if base > 0 or category["id"] in changes:
            needed[category["id"]] = max(0, base + changes.get(category["id"], 0))
    return needed


def group_totals(level, cents):
    """Cents per group: need / want / savings (Savings & debt)."""
    totals = {"need": 0, "want": 0, "savings": 0}
    for category in level["categories"]:
        totals[category["kind"]] += cents[category["id"]]
    return totals
