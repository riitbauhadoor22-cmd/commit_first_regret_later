# info_status.py — which financial information has the user given? Plain functions, no database.
# Every topic is in one of three states, and MISSING IS NEVER TREATED AS ZERO:
#   "provided" = there are real records (an income this month, an expense this month, a saved loan, a goal…)
#   "none"     = the user said there is nothing ("No income this month", "I don't have a loan"…)
#   "missing"  = the user hasn't told us yet → features that need it show a friendly prompt instead of numbers
from money import get_expenses_in_month, get_month_of, is_income_in_month

TOPICS = ("income", "expenses", "loans", "savings")
MONTHLY_TOPICS = ("income", "expenses")  # "none" is chosen per month; loans / savings are for the whole account


def choice_month(topic, month):
    """Month stored with a "none" choice: the month for income/expenses, "" for loans/savings."""
    return month if topic in MONTHLY_TOPICS else ""


def pick_state(has_records, chose_none):
    if has_records:
        return "provided"  # real records always win over an old "none" choice
    return "none" if chose_none else "missing"


def get_info_status(incomes, expenses, deposits, goals, savings, loans, choices, month):
    """{"income": state, "expenses": state, "loans": state, "savings": state} for this month.
    savings = the savings_settings row as a dict, or None if the user never saved one.
    choices = set of (topic, month) pairs the user marked as "none"."""
    has_savings = bool(goals) or any(get_month_of(d["date"]) <= month for d in deposits) or (
        savings is not None and (savings["bank_balance"] is not None or savings["monthly_target"] is not None))
    return {
        "income": pick_state(any(is_income_in_month(i, month) for i in incomes), ("income", month) in choices),
        "expenses": pick_state(bool(get_expenses_in_month(expenses, month)), ("expenses", month) in choices),
        "loans": pick_state(bool(loans), ("loans", "") in choices),
        "savings": pick_state(has_savings, ("savings", "") in choices),
    }


def is_known(state):
    """True when we can use the number (real records, or the user said it's none = 0)."""
    return state != "missing"
