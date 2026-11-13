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


# ===== GOAL CATEGORIES → CPI CATEGORY (edit here) =====
# Each savings-goal category and the Statistics Mauritius CPI category whose inflation it uses.
# Names on the right must match data/cpi_mauritius.csv exactly. Not listed / no category → "All Items".
GOAL_CPI_CATEGORIES = {
    "Phone": "Information and communication",
    "Laptop": "Information and communication",
    "Electronics": "Information and communication",
    "Games": "Recreation, sports and culture",
    "Hobbies": "Recreation, sports and culture",
    "Concerts": "Recreation, sports and culture",
    "Clothes": "Clothing and footwear",
    "Shoes": "Clothing and footwear",
    "Travel": "Transport",
    "Car": "Transport",
    "Transport": "Transport",
    "Course": "Education services",
    "Books": "Education services",
    "Food": "Food and non-alcoholic beverages",
    "Groceries": "Food and non-alcoholic beverages",
    "Events": "Restaurants and accommodation services",
    "Eating out": "Restaurants and accommodation services",
    "Holidays": "Restaurants and accommodation services",
    "Furniture": "Furnishings, household equipment and routine household maintenance",
    "Appliances": "Furnishings, household equipment and routine household maintenance",
    "Health": "Health",
    "Gym": "Health",
    "Other": "All Items",
}
