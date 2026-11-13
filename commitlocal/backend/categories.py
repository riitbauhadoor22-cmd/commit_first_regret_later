# categories.py — the fixed lists the app uses: spending categories (with their default Need/Want),
# income types, how often income repeats, and goal priorities.

# Each spending category and whether it is usually a "need" or a "want"
CATEGORIES = {
    "Groceries": "need",
    "Transport": "need",
    "Bills": "need",
    "Utilities": "need",
    "Food & drinks": "want",
    "Shopping": "want",
    "Subscriptions": "want",
    "Fun & outings": "want",
    "Other": "need",
}

INCOME_TYPES = ["Salary", "Allowance", "Side hustle", "Scholarship", "Other"]

FREQUENCIES = ["monthly", "weekly", "one-off"]

# 1 is the most important goal
PRIORITY_NAMES = {1: "High", 2: "Medium", 3: "Low"}


def get_default_kind(category):
    """'need' or 'want' for a category (unknown categories count as a need)."""
    return CATEGORIES.get(category, "need")
