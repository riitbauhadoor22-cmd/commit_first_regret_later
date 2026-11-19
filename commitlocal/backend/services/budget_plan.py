# services/budget_plan.py — budget plans: the starting plan from 4 answers, the monthly recommendation, judging a
# finished month against its plan, streaks, tips and what a looser plan costs. Plain maths on lists of dicts, no
# database (routes/plan.py reads the rows and enforces the commitment rules). Plans live in budget_plans.py.
import math
from datetime import date

from budget_plans import DEFAULT_PLAN, PLANS, is_looser
from money import get_fixed_bills, get_everyday_expenses, get_month_number, get_total, to_money
from services.month_summary import build_month_summary

# ===== SUGGESTION RULES (edit here) =====
NEEDS_SHARE_LIMIT = 0.60     # essentials (needs) above this share of income → zero-based
MIN_DATA_DAYS = 14           # the first expense is at least this old…
MIN_DATA_EXPENSES = 10       # …or at least this many expenses are logged → suggest from real spending
CAP_ROUND_TO = 50            # suggested caps are rounded down to Rs 50


# ===== MONTH HELPERS =====
def month_from_number(number):
    """The inverse of money.get_month_number: 24315 → '2026-03'."""
    year, month = divmod(number - 1, 12)
    return f"{year:04d}-{month + 1:02d}"


def add_months(month, count):
    return month_from_number(get_month_number(month) + count)


# ===== STARTING PLAN (no data yet) =====
def suggest_start_plan(life, pays_rent, has_loan, irregular_income):
    """(plan_id, reason code) from the start questions (the user's situation, not age). First match wins:
    loan → debt first · rent → 60% plan · irregular income → zero-based · studying (or both) → student caps ·
    otherwise 50/30/20."""
    if has_loan:
        return "debt_focus", "START_LOAN"
    if pays_rent:
        return "sixty_solution", "START_RENT"
    if irregular_income:
        return "zero_based", "START_IRREGULAR"
    if life in ("studying", "both"):
        return "student_caps", "START_STUDENT"
    return DEFAULT_PLAN, "START_DEFAULT"


# ===== PLAN HISTORY =====
def active_period(periods, month):
    """The plan period that covers `month` (YYYY-MM), or None. Two can cover one month only after a stricter plan
    started straight away: the newer one wins."""
    covering = [p for p in periods
                if p["start_month"] <= month and (p["end_month"] is None or p["end_month"] >= month)]
    return max(covering, key=lambda p: (p["start_month"], p["created_at"]), default=None)


def active_plan_id(periods, month):
    period = active_period(periods, month)
    return period["plan_id"] if period else None


def pending_period(periods, month):
    """A change asked for this month that starts next month (or later), if any."""
    return next((p for p in periods if p["start_month"] > month), None)


# ===== ONE MONTH'S FIGURES =====
def wants_by_category(expenses, month):
    """{category: spent} of this month's wants (everyday + fixed), biggest first."""
    rows = [e for e in get_everyday_expenses(expenses, month) + get_fixed_bills(expenses, month) if e["kind"] == "want"]
    totals = {}
    for row in rows:
        totals[row["category"]] = to_money(totals.get(row["category"], 0) + row["amount"])
    return dict(sorted(totals.items(), key=lambda item: -item[1]))


def month_figures(incomes, expenses, loans, savings_values, info, month, deposits=()):
    """What the plan maths needs for one month, from the app's ONE shared month summary. None = not known."""
    summary = build_month_summary(incomes, expenses, loans, savings_values, info, month, deposits=deposits)
    fixed_bills = get_total(get_fixed_bills(expenses, month)) if summary["spent"] is not None else None
    loan_payments = summary["loan_repayments"] or 0
    return {"month": month, "income": summary["income"], "needs": summary["needs"], "wants": summary["wants"],
            "saved": summary["saved"], "loans": loan_payments, "savings_state": summary["info"]["savings"],
            "savings_status": summary["savings_status"],
            "fixed_costs": to_money(fixed_bills + loan_payments) if fixed_bills is not None else None,
            "wants_by_category": wants_by_category(expenses, month) if summary["spent"] is not None else {}}


def share(part, income):
    return part / income if income else 0.0


def plan_buckets(figures, plan_id):
    """(needs, wants, savings) in rupees for a plan. Loan repayments are needs, except in "Debt first" where they
    count towards the savings/debt part."""
    loans_in_savings = PLANS[plan_id].get("loans_in_savings", False)
    needs = (figures["needs"] or 0) + (0 if loans_in_savings else figures["loans"])
    savings = (figures["saved"] or 0) + (figures["loans"] if loans_in_savings else 0)
    return to_money(needs), to_money(figures["wants"] or 0), to_money(savings)


def plan_progress(figures, plan_id):
    """This month so far: actual % of income per part next to the plan's aim. None when there is no income."""
    income = figures["income"]
    if not income or income <= 0 or figures["needs"] is None:
        return None
    needs, wants, savings = plan_buckets(figures, plan_id)
    plan = PLANS[plan_id]
    progress = {part: {"actual": round(amount / income * 100, 1), "aim": plan[part]}
                for part, amount in (("needs", needs), ("wants", wants), ("savings", savings))}
    if savings_not_tracked(figures, plan_id):
        progress["savings"]["actual"] = None  # "Savings not tracked yet", never a red 0%
    return progress


def savings_not_tracked(figures, plan_id):
    """Savings never added (state missing): the savings part isn't judged, so it can't make a month "off plan".
    In "Debt first" loan repayments still count as that part."""
    return figures.get("savings_state") == "missing" and not (PLANS[plan_id].get("loans_in_savings") and figures["loans"])


# ===== JUDGING A FINISHED MONTH =====
def judge_month(figures, plan_id):
    """on_plan / over / no_data + how far over (Rs). On plan = needs and wants not above the plan's share of income
    and the plan's saving reached. Anything under Rs 1 is rounding, not overspending."""
    income = figures["income"]
    if not income or income <= 0 or figures["needs"] is None:
        return {"status": "no_data", "needs_over": 0.0, "wants_over": 0.0, "savings_short": 0.0, "details": {}}
    plan = PLANS[plan_id]
    needs, wants, savings = plan_buckets(figures, plan_id)

    def gap(amount):
        return to_money(amount) if amount >= 1 else 0.0
    result = {
        "needs_over": gap(needs - income * plan["needs"] / 100),
        "wants_over": gap(wants - income * plan["wants"] / 100),
        "savings_short": 0.0 if savings_not_tracked(figures, plan_id) else gap(income * plan["savings"] / 100 - savings),
    }
    biggest = next(iter(figures["wants_by_category"].items()), None)
    result["details"] = {
        "savings_tracked": not savings_not_tracked(figures, plan_id),
        "percent": {"needs": round(share(needs, income) * 100, 1), "wants": round(share(wants, income) * 100, 1),
                    "savings": round(share(savings, income) * 100, 1)},
        "biggest_want": {"category": biggest[0], "amount": biggest[1]} if biggest else None,
        "caps": category_caps(figures["wants_by_category"], income, plan_id) if result["wants_over"] else [],
    }
    result["status"] = "over" if any(result[k] for k in ("needs_over", "wants_over", "savings_short")) else "on_plan"
    return result


def category_caps(wants, income, plan_id):
    """Suggested caps per want category that fit the plan's wants share: each category shrinks by the same factor,
    rounded down to Rs 50. Only when wants are above the plan."""
    budget = income * PLANS[plan_id]["wants"] / 100
    total = sum(wants.values())
    if not total or total <= budget:
        return []
    factor = budget / total
    return [{"category": category, "spent": spent,
             "cap": float(math.floor(spent * factor / CAP_ROUND_TO) * CAP_ROUND_TO)}
            for category, spent in wants.items()]


def month_tips(result):
    """1–2 concrete tips for next month (codes + numbers for the translated text). Never "pick a looser plan"."""
    tips = []
    details = result.get("details") or {}
    if result["wants_over"]:
        caps = details.get("caps") or []
        if caps:
            tips.append({"code": "CAP_CATEGORY", "category": caps[0]["category"], "cap": caps[0]["cap"]})
        tips.append({"code": "NO_SPEND_WEEK", "amount": result["wants_over"]})
    if result["savings_short"] and len(tips) < 2:
        tips.append({"code": "SAVE_ON_PAYDAY", "amount": result["savings_short"]})
    if result["needs_over"] and len(tips) < 2:
        tips.append({"code": "REVIEW_BILLS", "amount": result["needs_over"]})
    return tips[:2]


def count_streak(results):
    """Months on plan in a row, ending with the newest finished month. A month over, without data or missing
    breaks the streak."""
    by_month = {r["month"]: r["status"] for r in results}
    if not by_month:
        return 0
    month, streak = max(by_month), 0
    while by_month.get(month) == "on_plan":
        streak += 1
        month = add_months(month, -1)
    return streak


# ===== STYLE SUGGESTION FROM REAL SPENDING (simple rules, no AI) =====
def has_enough_data(expenses, today):
    """Enough to suggest from real spending: the first expense is 14+ days old, or 10+ expenses are logged."""
    if not expenses:
        return False
    first = min(e["date"] for e in expenses)
    days = (date.fromisoformat(today) - date.fromisoformat(first)).days
    return days >= MIN_DATA_DAYS or len(expenses) >= MIN_DATA_EXPENSES


def suggest_style(figures):
    """(plan_id, rule code, numbers) from one month's figures:
    no income recorded → zero-based · essentials (needs) > 60% of income → zero-based · otherwise → pay yourself
    first. numbers = what the reason line shows ("Your essentials are 68% of your income, so…")."""
    income = figures["income"]
    if not income or income <= 0:
        return "zero_based", "NO_INCOME", {"months": [figures["month"]]}
    percent = round(share(figures["needs"] or 0, income) * 100)
    numbers = {"percent": percent, "months": [figures["month"]], "limit": round(NEEDS_SHARE_LIMIT * 100)}
    if share(figures["needs"] or 0, income) > NEEDS_SHARE_LIMIT:
        return "zero_based", "NEEDS_HIGH", numbers
    return "pay_yourself_first", "NEEDS_OK", numbers


def wants_over_plan(figures, plan_id):
    """Spending more on wants than the current plan allows (a share of income)."""
    income = figures["income"]
    return bool(income) and income > 0 and share(figures["wants"] or 0, income) * 100 > PLANS[plan_id]["wants"]


def build_recommendation(figures, current_plan_id):
    """{"action": "switch" | "keep", "plan_id", "rule", "numbers", "looser"} for one month's figures.
    Commitment rule: spending too much on wants never unlocks a looser plan (one that saves less or allows more
    wants); the user keeps their plan and gets spending caps in the monthly tips instead."""
    plan_id, rule, numbers = suggest_style(figures)
    keep = {"action": "keep", "plan_id": current_plan_id, "rule": rule, "numbers": numbers, "looser": False}
    if plan_id == current_plan_id:
        return keep  # the current style already fits
    looser = is_looser(plan_id, current_plan_id)
    if looser and wants_over_plan(figures, current_plan_id):
        return {**keep, "rule": "WANTS_OVER"}
    return {"action": "switch", "plan_id": plan_id, "rule": rule, "numbers": numbers, "looser": looser}


# ===== WHAT A LOOSER PLAN COSTS =====
def months_to_goal(goal, monthly_saving):
    left = max(goal["target_amount"] - goal["saved_amount"], 0)
    if left == 0:
        return 0
    if monthly_saving <= 0:
        return None  # never, at this rate
    return math.ceil(left / monthly_saving)


def switch_cost(current_id, new_id, income, goal):
    """Rs a month saved less with the new plan, and how many months later the goal would be reached
    (None = never at the new rate; no goal / no income → no goal line)."""
    income = income or 0
    current_saving = income * PLANS[current_id]["savings"] / 100
    new_saving = income * PLANS[new_id]["savings"] / 100
    cost = {"save_less": to_money(max(current_saving - new_saving, 0)), "goal": None}
    if goal and income > 0:
        before, after = months_to_goal(goal, current_saving), months_to_goal(goal, new_saving)
        later = None if after is None or before is None else max(after - before, 0)
        cost["goal"] = {"name": goal["name"], "months_later": later}
    return cost
