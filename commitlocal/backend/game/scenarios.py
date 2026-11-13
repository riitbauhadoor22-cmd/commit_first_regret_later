# game/scenarios.py — every number of the Arcade "Budget Challenge" in ONE place (edit here to change the game).
# Fictional Mauritius scenarios for 16–25 year olds. Amounts are rupees. Served by GET /api/game/levels.
# Texts are NOT here: the frontend translates ids with lang/*.json ("game.levelTitle.<n>", "game.cat.<id>", "game.event.<id>").
#
# Category fields: id, kind = group ("need" = Needs 50% · "want" = Wants 30% · "savings" = Savings & debt 20%),
#   min_amount → ESSENTIAL category: must get at least this ("Suggested at least Rs X"),
#   locked     → fixed commitment: pre-filled, can't be changed (loan repayments sit in the Savings & debt group).
# Event fields: id, type, category, amount:
#   "cost"     → the category needs `amount` more (its minimum goes up),
#   "discount" → the category needs `amount` less (its minimum goes down, never below 0),
#   "bonus"    → `amount` is added to the income.

# ===== SCORING RULES (points out of 100) =====
POINTS = {"balance": 30, "essentials": 25, "allocation": 20, "savings": 15, "events": 10}
GUIDE = {"need": 50, "want": 30, "savings": 20}  # the 50·30·20 guideline (percent of income)
BUFFER_PERCENT = 10           # up to 10% of income left unallocated still counts as a sensible buffer
SAVINGS_GOAL_PERCENT = 10     # the Savings category reaching 10% of income gets full savings points (no extra above)
SPLIT_FULL_WITHIN = 10        # allocation distance (percentage points) still worth full allocation points
SPLIT_ZERO_AT = 50            # distance where allocation points reach 0
XP_FIRST_COMPLETION_BONUS = 20  # one-time bonus the first time each level is completed

# ===== LEVELS =====
LEVELS = [
    {
        "level": 1, "income": 15000,  # Student Life
        "categories": [
            {"id": "food", "kind": "need", "min_amount": 4000},
            {"id": "transport", "kind": "need", "min_amount": 1500},
            {"id": "phone", "kind": "need", "min_amount": 500},
            {"id": "study", "kind": "need", "min_amount": 600},
            {"id": "entertainment", "kind": "want"},
            {"id": "personal", "kind": "want"},
            {"id": "savings", "kind": "savings"},
        ],
        "events": [
            {"id": "bus_fare", "type": "cost", "category": "transport", "amount": 500},
            {"id": "grocery_discount", "type": "discount", "category": "food", "amount": 300},
            {"id": "charger", "type": "cost", "category": "phone", "amount": 400},
            {"id": "small_bonus", "type": "bonus", "category": "savings", "amount": 1000},
        ],
    },
    {
        "level": 2, "income": 30000,  # First Job
        "categories": [
            {"id": "rent_household", "kind": "need", "min_amount": 6500},
            {"id": "groceries", "kind": "need", "min_amount": 4000},
            {"id": "transport", "kind": "need", "min_amount": 2000},
            {"id": "utilities", "kind": "need", "min_amount": 1200},
            {"id": "phone", "kind": "need", "min_amount": 800},
            {"id": "entertainment", "kind": "want"},
            {"id": "shopping", "kind": "want"},
            {"id": "savings", "kind": "savings"},
            {"id": "loan", "kind": "savings", "locked": 2500},
        ],
        "events": [
            {"id": "bus_fare", "type": "cost", "category": "transport", "amount": 700},
            {"id": "grocery_discount", "type": "discount", "category": "groceries", "amount": 500},
            {"id": "utility_rise", "type": "cost", "category": "utilities", "amount": 600},
            {"id": "small_bonus", "type": "bonus", "category": "savings", "amount": 1500},
        ],
    },
    {
        "level": 3, "income": 45000,  # Independent Living
        "categories": [
            {"id": "rent", "kind": "need", "locked": 12000},
            {"id": "groceries", "kind": "need", "min_amount": 4000},
            {"id": "electricity_water", "kind": "need", "min_amount": 1500},
            {"id": "transport", "kind": "need", "min_amount": 1500},
            {"id": "phone", "kind": "need", "min_amount": 800},
            {"id": "healthcare", "kind": "need", "min_amount": 700},
            {"id": "entertainment", "kind": "want"},
            {"id": "personal", "kind": "want"},
            {"id": "savings", "kind": "savings"},
            {"id": "loan", "kind": "savings", "locked": 3000},
        ],
        "events": [
            {"id": "utility_rise", "type": "cost", "category": "electricity_water", "amount": 900},
            {"id": "medical_bill", "type": "cost", "category": "healthcare", "amount": 1200},
            {"id": "grocery_discount", "type": "discount", "category": "groceries", "amount": 600},
            {"id": "small_bonus", "type": "bonus", "category": "savings", "amount": 2000},
        ],
    },
]


# ===== LOOKUPS =====
def get_level(number):
    """One level's config, or None if it doesn't exist."""
    return next((level for level in LEVELS if level["level"] == number), None)


def get_event(level, event_id):
    return next((event for event in level["events"] if event["id"] == event_id), None)


def minimum_of(category):
    """Rupees an essential category needs (locked amount or min_amount); 0 for optional ones."""
    return category.get("locked", category.get("min_amount", 0))
