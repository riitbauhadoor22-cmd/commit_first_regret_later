# money.py — all the money maths. These are plain functions: they take lists of rows (dicts)
# and return numbers. They never touch the database, so they are easy to test (see tests/test_money.py).
#
# Dates are text "YYYY-MM-DD" and months are text "YYYY-MM". Text like this sorts in date order,
# so "2026-10" < "2026-11" works as you would expect.
from datetime import date, timedelta

from categories import CATEGORIES, PRIORITY_NAMES

WEEKS_PER_MONTH = 52 / 12
QUICK_ADD_DAYS = 30
QUICK_ADD_COUNT = 4
SAFETY_NET_MONTHS = 3
DEFAULT_SAVING_SHARE = 0.20  # the "20" in the 50/30/20 rule


# ===== SMALL HELPERS =====
def get_today():
    """Today as 'YYYY-MM-DD'."""
    return date.today().isoformat()


def get_this_month():
    """This month as 'YYYY-MM'."""
    return get_today()[:7]


def to_money(number):
    """Round to 2 decimal places (paise)."""
    return round(number + 0.0, 2)


def to_cents(rupees):
    """Rupees -> whole cents for the database: 150.5 -> 15050."""
    return int(round(rupees * 100))


def to_rupees(cents):
    """Whole cents from the database -> rupees for the API: 15050 -> 150.5."""
    return cents / 100


def get_month_of(date_text):
    """'2026-11-13' -> '2026-11'"""
    return date_text[:7]


def get_month_number(month_text):
    """'2026-11' -> a single counting number (year × 12 + month), so months can be subtracted."""
    year, month = month_text.split("-")
    return int(year) * 12 + int(month)


def starts_by_month(start_date, month):
    """True if something that repeats from start_date is counted in this month."""
    return get_month_of(start_date) <= month


def get_percent(part, whole):
    """part ÷ whole × 100, rounded to 1 decimal. 0 if whole is 0."""
    if whole <= 0:
        return 0.0
    return round(part / whole * 100, 1)


# ===== INCOME =====
def get_income_per_month(income):
    """How much one income adds to a month. Weekly income: amount × 52 ÷ 12."""
    if income["frequency"] == "weekly":
        return income["amount"] * WEEKS_PER_MONTH
    return income["amount"]


def is_income_in_month(income, month):
    """One-offs count only in the month they were received; repeating income from its start month on."""
    if income["frequency"] == "one-off":
        return get_month_of(income["date"]) == month
    return starts_by_month(income["date"], month)


def get_monthly_income(incomes, month):
    """Regular monthly + weekly × 52 ÷ 12 + one-offs dated this month."""
    total = 0
    for income in incomes:
        if is_income_in_month(income, month):
            total += get_income_per_month(income)
    return to_money(total)


def get_regular_income(incomes, month):
    """Only repeating income (monthly + weekly), no one-offs. Used for the default saving target."""
    total = 0
    for income in incomes:
        if income["frequency"] != "one-off" and is_income_in_month(income, month):
            total += get_income_per_month(income)
    return to_money(total)


# ===== EXPENSES =====
def get_fixed_bills(expenses, month):
    """Fixed bills (repeat every month) that count in this month."""
    return [e for e in expenses if e["is_fixed"] and starts_by_month(e["date"], month)]


def get_everyday_expenses(expenses, month):
    """Normal (not fixed) expenses dated in this month."""
    return [e for e in expenses if not e["is_fixed"] and get_month_of(e["date"]) == month]


def get_expenses_in_month(expenses, month):
    return get_fixed_bills(expenses, month) + get_everyday_expenses(expenses, month)


def get_total(rows):
    return to_money(sum(row["amount"] for row in rows))


def get_total_spent(expenses, month):
    """Fixed bills + everyday expenses dated this month."""
    return get_total(get_expenses_in_month(expenses, month))


def get_total_by_kind(expenses, month, kind):
    """Total of this month's expenses that are 'need' (or 'want')."""
    return get_total([e for e in get_expenses_in_month(expenses, month) if e["kind"] == kind])


def get_category_spending(expenses, budgets, month):
    """One row per category: everyday spending this month, its budget, and how far over it is.
    Fixed bills are not in here: they have their own card."""
    limits = {b["category"]: b["monthly_limit"] for b in budgets}
    everyday = get_everyday_expenses(expenses, month)
    rows = []
    for category in CATEGORIES:
        spent = get_total([e for e in everyday if e["category"] == category])
        budget = limits.get(category)
        over_by = to_money(spent - budget) if budget is not None and spent > budget else 0
        rows.append({
            "category": category,
            "default_kind": CATEGORIES[category],
            "spent": spent,
            "budget": budget,
            "percent": get_percent(spent, budget) if budget else 0.0,
            "over_by": over_by,
        })
    return rows


# ===== SAVINGS =====
def get_saved_in_month(deposits, month):
    """All deposits (goals + safety net) dated this month."""
    return get_total([d for d in deposits if get_month_of(d["date"]) == month])


def get_monthly_target(custom_target, incomes, month):
    """The user's own target if they set one, otherwise 20% of regular income.
    None = unknown (no own target and no regular income): never shown as a Rs 0 target."""
    if custom_target is not None:
        return to_money(custom_target)
    regular = get_regular_income(incomes, month)
    if regular <= 0:
        return None
    return to_money(regular * DEFAULT_SAVING_SHARE)


def get_safety_net(expenses, safety_net_saved, month):
    """Target = 3 × fixed monthly bills. Percent is capped at 100."""
    target = to_money(get_total(get_fixed_bills(expenses, month)) * SAFETY_NET_MONTHS)
    percent = min(get_percent(safety_net_saved, target), 100.0)
    return {"target": target, "saved": to_money(safety_net_saved), "percent": percent}


def get_amount_to_add(amount, target, saved):
    """How much of a deposit a goal can take: never more than it still needs."""
    still_needed = max(target - saved, 0)
    return to_money(min(amount, still_needed))


def get_bank_bar(bank_balance, safety_net_saved, goals):
    """Splits the bank balance into: safety net, one part per goal, and 'Free' money.
    Each part gets a percent of the bar's width. bank_balance None (not added) → no 'Free' money is guessed."""
    if bank_balance is None:
        bank_balance = 0
    parts = [{"label": "Safety net", "amount": to_money(safety_net_saved), "goal_id": None}]
    for goal in goals:
        parts.append({"label": goal["name"], "amount": to_money(goal["saved_amount"]), "goal_id": goal["id"]})
    assigned = sum(p["amount"] for p in parts)
    parts.append({"label": "Free", "amount": to_money(max(bank_balance - assigned, 0)), "goal_id": None})

    # If the bank balance is lower than what's assigned, the bar is as long as the assigned total
    bar_total = max(bank_balance, assigned)
    for part in parts:
        part["percent"] = get_percent(part["amount"], bar_total)
    return parts


# ===== GOALS =====
def get_months_left(today, deadline):
    """Months from this month to the deadline's month, at least 1."""
    months = get_month_number(get_month_of(deadline)) - get_month_number(get_month_of(today))
    return max(months, 1)


def get_needs_per_month(goal, today):
    """(target − saved) ÷ months left."""
    still_needed = max(goal["target_amount"] - goal["saved_amount"], 0)
    return to_money(still_needed / get_months_left(today, goal["deadline"]))


def sort_goals_by_priority(goals):
    """High priority first; same priority → earlier deadline first."""
    return sorted(goals, key=lambda g: (g["priority"], g["deadline"], g["created_at"]))


def get_goal_statuses(goals, monthly_target, today):
    """Hand out the monthly saving target to goals in priority order.
    A goal that gets at least what it needs is 'On track'; otherwise 'Needs more'.
    No known target (None) → 'No target': we can't say if it's on track, so we don't guess."""
    money_left = monthly_target
    results = []
    for goal in sort_goals_by_priority(goals):
        needs = get_needs_per_month(goal, today)
        if needs == 0:
            status = "Done"
        elif monthly_target is None:
            status = "No target"
        else:
            given = min(needs, money_left)
            money_left -= given
            status = "On track" if given >= needs else "Needs more"
        results.append({
            **goal,
            "priority_name": PRIORITY_NAMES.get(goal["priority"], "Low"),
            "percent": min(get_percent(goal["saved_amount"], goal["target_amount"]), 100.0),
            "needs_per_month": needs,
            "status": status,
        })
    return results


def get_goals_warning(total_needed, monthly_target):
    """A warning message when all goals together need more than the monthly saving target."""
    if monthly_target is None or total_needed <= monthly_target:
        return None
    return (f"Your goals need Rs {format_rupees(total_needed)} a month, but you save "
            f"Rs {format_rupees(monthly_target)}. Push a date back or focus on one goal first.")


def format_rupees(amount):
    """Indian style grouping: 3700 -> '3,700'   150000 -> '1,50,000'   245.5 -> '245.50'"""
    whole = int(abs(amount))
    paise = round((abs(amount) - whole) * 100)
    digits = str(whole)
    text = digits[-3:]
    rest = digits[:-3]
    while rest:  # after the last 3 digits, India groups in twos
        text = rest[-2:] + "," + text
        rest = rest[:-2]
    if paise:
        text += f".{paise:02d}"
    return ("-" if amount < 0 else "") + text


# ===== QUICK ADD =====
def get_quick_add(expenses, today):
    """The 4 most repeated everyday expenses (same note + amount) from the last 30 days.
    Ties go to the one used most recently."""
    first_day = (date.fromisoformat(today) - timedelta(days=QUICK_ADD_DAYS)).isoformat()
    groups = {}
    for e in expenses:
        if e["is_fixed"] or not (first_day <= e["date"] <= today):
            continue
        key = (e["note"].strip().lower(), e["amount"])
        if key not in groups:
            groups[key] = {"count": 0, "latest": e}
        group = groups[key]
        group["count"] += 1
        if (e["date"], e["created_at"]) > (group["latest"]["date"], group["latest"]["created_at"]):
            group["latest"] = e

    ranked = sorted(groups.values(),
                    key=lambda g: (g["count"], g["latest"]["date"], g["latest"]["created_at"]), reverse=True)
    chips = []
    for group in ranked[:QUICK_ADD_COUNT]:
        latest = group["latest"]
        chips.append({
            "note": latest["note"],
            "amount": latest["amount"],
            "category": latest["category"],
            "kind": latest["kind"],
            "label": f"{latest['note'] or latest['category']} Rs {format_rupees(latest['amount'])}",
            "times": group["count"],
        })
    return chips


# ===== MONEY TAB SUMMARY =====
def percent_or_none(part, whole):
    """part ÷ whole × 100, or None when either is unknown or there's no income to divide by."""
    if part is None or whole is None or whole <= 0:
        return None
    return get_percent(part, whole)


def get_summary(incomes, expenses, deposits, budgets, month, info=None):
    """Everything the Money tab's dark card and category rows need for one month.
    info = {"income": state, "expenses": state, "savings": state} (see info_status.py). A "missing" topic gives
    None instead of a number, so the screen asks for it instead of showing Rs 0. info None = everything known."""
    info = info or {}
    income_known = info.get("income", "provided") != "missing"
    expenses_known = info.get("expenses", "provided") != "missing"
    saved = get_saved_in_month(deposits, month)
    saved_known = saved > 0 or info.get("savings", "provided") != "missing"
    income = get_monthly_income(incomes, month) if income_known else None
    spent = get_total_spent(expenses, month) if expenses_known else None
    needs = get_total_by_kind(expenses, month, "need") if expenses_known else None
    wants = get_total_by_kind(expenses, month, "want") if expenses_known else None
    fixed = get_fixed_bills(expenses, month)
    recent = sorted(get_everyday_expenses(expenses, month), key=lambda e: (e["date"], e["created_at"]), reverse=True)
    # Left to spend needs BOTH income and spending; recorded deposits are taken off (none recorded = nothing put away)
    left = to_money(income - spent - saved) if income is not None and spent is not None else None
    return {
        "month": month,
        "info": {"income": info.get("income", "provided"), "expenses": info.get("expenses", "provided"),
                 "savings": info.get("savings", "provided")},
        "income": income,
        "spent": spent,
        "saved": saved if saved_known else None,
        "left_to_spend": left,
        "needs_percent": percent_or_none(needs, income),
        "wants_percent": percent_or_none(wants, income),
        "savings_percent": percent_or_none(saved if saved_known else None, income),
        "categories": get_category_spending(expenses, budgets, month),
        "fixed_bills": fixed,
        "fixed_total": get_total(fixed),
        "recent": recent[:3],
    }
