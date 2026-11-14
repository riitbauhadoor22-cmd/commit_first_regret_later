# services/forecast.py — the spending forecast and the goal "ready by" dates. Plain maths on the user's own rows
# (never the AI, never the database: easy to test, see tests/backend/test_forecast.py).
#   Spending forecast = everyday spent so far ÷ days passed × days in the month + fixed bills + loan repayments
#                       (bills and loans counted once, not per day).
#   Left at month end  = income − forecast spending − saved_this_month (from services/month_summary.py; the bank
#                        balance is never part of it).
#   Goal ETA           = (target − saved) ÷ average saved into that goal per month (last 3 months).
# Not enough data → {"available": False, "reason": CODE}: the screen shows nothing instead of a silly guess.
import calendar
import math
from datetime import date

from money import (get_everyday_expenses, get_fixed_bills, get_month_number, get_month_of, get_monthly_income,
                   get_total, to_money)

MIN_DAYS = 5               # before the 5th of the month one big shop would make the guess jump around
GOAL_HISTORY_MONTHS = 3    # the average saved per month uses up to the last 3 months
MAX_ETA_MONTHS = 1200      # more than 100 years away = not a useful date


# ===== HELPERS =====
def month_from_number(number):
    """get_month_number's opposite (year × 12 + month): 24324 → '2026-12'."""
    year, month = divmod(number - 1, 12)
    return f"{year:04d}-{month + 1:02d}"


def not_available(reason):
    return {"available": False, "reason": reason}


# ===== SPENDING FORECAST =====
def build_spending_forecast(incomes, expenses, budgets, saved_this_month, today, month=None, loan_repayments=0):
    """today = a date (the phone's local day). Only the CURRENT month can be forecast. Normally called through
    services/month_summary.build_month_summary, which passes saved_this_month and the loan repayments."""
    this_month = today.isoformat()[:7]
    month = month or this_month
    if month != this_month:
        return not_available("OTHER_MONTH")
    if today.day < MIN_DAYS:
        return not_available("TOO_EARLY")
    # Everyday spending up to today (an expense typed with a later date isn't "so far")
    so_far = [e for e in get_everyday_expenses(expenses, month) if e["date"] <= today.isoformat()]
    if not so_far:
        return not_available("NO_SPENDING")

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    everyday_so_far = get_total(so_far)
    fixed_total = get_total(get_fixed_bills(expenses, month))
    # fixed bills and loan repayments once, not per day
    forecast = to_money(everyday_so_far / today.day * days_in_month + fixed_total + loan_repayments)

    limits = [b["monthly_limit"] for b in budgets if b.get("monthly_limit") is not None]
    budget = to_money(sum(limits)) if limits else None  # overall budget = sum of category budgets (none set → None)
    income = get_monthly_income(incomes, month)
    planned_savings = to_money(saved_this_month or 0)
    left = to_money(income - forecast - planned_savings) if income > 0 else None  # no income → no "left" guess
    return {
        "available": True,
        "month": month,
        "days_passed": today.day,
        "days_in_month": days_in_month,
        "last_day": date(today.year, today.month, days_in_month).isoformat(),
        "everyday_so_far": everyday_so_far,
        "fixed_bills": fixed_total,
        "loan_repayments": to_money(loan_repayments),
        "forecast_spent": forecast,
        "budget": budget,
        "over_budget": budget is not None and forecast > budget,
        "income": income if income > 0 else None,
        "planned_savings": planned_savings,
        "left_at_month_end": left,
    }


# ===== GOAL ETA =====
def get_goal_eta(goal, deposits, today):
    """{per_month, months, eta_month} for one goal, or None (done, or nothing saved into it in the last 3 months)."""
    remaining = goal["target_amount"] - goal["saved_amount"]
    if remaining <= 0:
        return None
    this_number = get_month_number(today.isoformat()[:7])
    first_number = this_number - GOAL_HISTORY_MONTHS + 1
    recent = [d for d in deposits if d.get("goal_id") == goal["id"]
              and first_number <= get_month_number(get_month_of(d["date"])) <= this_number]
    if not recent:
        return None
    # Months counted = from the first recent deposit's month to this month (a goal started last month isn't ÷ 3)
    started = min(get_month_number(get_month_of(d["date"])) for d in recent)
    per_month = get_total(recent) / (this_number - started + 1)
    if per_month <= 0:
        return None
    months = math.ceil(round(remaining / per_month, 6))  # round first: 3.0000001 must stay 3
    if months > MAX_ETA_MONTHS:
        return None
    return {"per_month": to_money(per_month), "months": months, "eta_month": month_from_number(this_number + months)}


def build_goal_etas(goals, deposits, today):
    """{goal id: eta} for the goals that have one (goals without enough history are simply left out)."""
    etas = {}
    for goal in goals:
        eta = get_goal_eta(goal, deposits, today)
        if eta is not None:
            etas[goal["id"]] = eta
    return etas
