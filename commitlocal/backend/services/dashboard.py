# services/dashboard.py — every number on the Dashboard tab, worked out from the user's own records. NO AI, no made-up
# figures: plain functions (no database) so they are easy to test. Each part says when it can't be worked out
# ("available": false + a reason code) instead of showing Rs 0.
#   balance (this month) · spending per month · saving rate per month · loan projection · monthly recap
#   financial health score · weekly budget + badges · savings jar (goals)
# Dates are "YYYY-MM-DD" text in the user's LOCAL time ("today" comes from the phone), months are "YYYY-MM".
from datetime import date, timedelta

from info_status import get_info_status, is_known
from money import (get_category_spending, get_expenses_in_month, get_goal_statuses, get_month_of, get_monthly_income,
                   get_monthly_target, get_percent, get_saved_in_month, get_total, get_total_by_kind, get_total_spent,
                   to_money)
from services.financial_analysis import get_previous_month

MONTHS_SHOWN = 6           # graphs show at most the last 6 months that HAVE data
MAX_LOAN_MONTHS = 360      # projections stop after 30 years
STABLE_POINTS = 2          # saving-rate changes under 2 points count as "stable"
NEUTRAL_BALANCE = 1        # |balance| under Rs 1 = neutral
MIN_TRACKED_DAYS = 3       # a week only counts for badges if spending was recorded on 3+ different days
SCORE_MIN_WEIGHT = 50      # fewer than 50 of the 100 points measurable → "Not enough data yet"
SAVINGS_GUIDE = 20         # the 20% reference line


# ===== MONTH HELPERS =====
def get_recent_months(month, count=MONTHS_SHOWN):
    """The `count` months up to and including `month`, oldest first."""
    months = [month]
    while len(months) < count:
        months.insert(0, get_previous_month(months[0]))
    return months


def get_month_status(records, choices, month):
    """provided / none / missing for every topic in one month (info_status.py)."""
    return get_info_status(records["incomes"], records["expenses"], records["deposits"], records["goals"],
                           records["savings_row"], records["loans"], choices, month)


def loan_counts_in_month(loan, month):
    """A saved loan's repayment counts from its start month (or the month it was saved) onwards."""
    start = loan["start_date"] or loan["created_at"][:10]
    return get_month_of(start) <= month


def get_loan_payments(loans, month):
    return get_total([{"amount": loan["monthly_payment"]} for loan in loans if loan_counts_in_month(loan, month)])


def change_percent(before, now):
    """% change from before to now (None if before is 0 or unknown)."""
    if before is None or now is None or before <= 0:
        return None
    return round((now - before) / before * 100, 1)


# ===== 1. BALANCE (this month) =====
def get_month_balance(records, choices, month):
    """Available this month = income − expenses − loan repayments − savings contributions.
    Savings contributions are deposits into goals / the safety net: they are NOT expenses in this app, so they are
    taken off once. Needs income and expenses to be known (given, or "none"); unknown loans are left out (flagged)."""
    status = get_month_status(records, choices, month)
    missing = [topic for topic in ("income", "expenses") if not is_known(status[topic])]
    if missing:
        return {"available": False, "month": month, "missing": missing}
    loans_known = is_known(status["loans"])
    income = get_monthly_income(records["incomes"], month)
    spent = get_total_spent(records["expenses"], month)
    saved = get_saved_in_month(records["deposits"], month)
    loans = get_loan_payments(records["loans"], month) if loans_known else 0
    balance = to_money(income - spent - saved - loans)
    state = "neutral" if abs(balance) < NEUTRAL_BALANCE else ("positive" if balance > 0 else "negative")
    return {"available": True, "month": month, "income": income, "expenses": spent, "savings": saved,
            "loan_repayments": loans if loans_known else None, "balance": balance, "state": state,
            "excludes_loans": not loans_known}


def build_balance(records, choices, month, savings_values):
    current = get_month_balance(records, choices, month)
    previous = get_month_balance(records, choices, get_previous_month(month))
    put_aside = to_money(sum(goal["saved_amount"] for goal in records["goals"]) + savings_values["safety_net_saved"])
    current["put_aside"] = put_aside  # money already in goals + safety net (kept apart from available cash)
    current["bank_balance"] = savings_values["bank_balance"]  # None = not added
    if current["available"] and previous["available"]:
        current["previous_balance"] = previous["balance"]
        current["change"] = to_money(current["balance"] - previous["balance"])
    else:
        current["previous_balance"] = None
        current["change"] = None
    return current


# ===== 2. SPENDING PER MONTH =====
def build_spending_series(expenses, month):
    """Only months that HAVE recorded spending (no made-up zero months). Total + per category + change vs the
    calendar month before (when that month has data too)."""
    points = []
    for each in get_recent_months(month):
        rows = get_expenses_in_month(expenses, each)
        if not rows:
            continue
        by_category = {}
        for row in rows:
            by_category[row["category"]] = to_money(by_category.get(row["category"], 0) + row["amount"])
        previous_rows = get_expenses_in_month(expenses, get_previous_month(each))
        total = get_total(rows)
        points.append({"month": each, "total": total, "by_category": by_category,
                       "change_percent": change_percent(get_total(previous_rows), total) if previous_rows else None})
    return {"available": bool(points), "months": points}


# ===== 3. SAVING RATE PER MONTH =====
def get_first_savings_month(deposits, goals):
    months = [get_month_of(d["date"]) for d in deposits] + [get_month_of(g["created_at"][:10]) for g in goals]
    return min(months) if months else None


def build_savings_series(records, choices, month):
    """Saving rate = savings contributions (deposits) ÷ take-home income × 100, for months with income given
    and from the month the user started saving (a goal or a deposit). Before that, nothing is shown (not 0%)."""
    first = get_first_savings_month(records["deposits"], records["goals"])
    if first is None:
        return {"available": False, "reason": "NO_SAVINGS", "months": [], "guide": SAVINGS_GUIDE, "trend": None}
    points = []
    for each in get_recent_months(month):
        if each < first or get_month_status(records, choices, each)["income"] != "provided":
            continue
        income = get_monthly_income(records["incomes"], each)
        saved = get_saved_in_month(records["deposits"], each)
        points.append({"month": each, "saved": saved, "income": income, "rate": get_percent(saved, income)})
    if not points:
        return {"available": False, "reason": "NO_INCOME", "months": [], "guide": SAVINGS_GUIDE, "trend": None}
    trend = None
    if len(points) >= 2:
        difference = points[-1]["rate"] - points[-2]["rate"]
        trend = "stable" if abs(difference) < STABLE_POINTS else ("up" if difference > 0 else "down")
    return {"available": True, "months": points, "guide": SAVINGS_GUIDE, "trend": trend}


# ===== 4. LOAN PROJECTION =====
def project_loan(balance, annual_rate, payment, start_month):
    """Month-by-month outstanding balance with a fixed rate and repayment (an ESTIMATE: rates can change,
    payments can be missed or made early). payoff_month None when the repayment doesn't cover the interest."""
    if balance is None or annual_rate is None or payment is None or payment <= 0:
        return {"available": False, "reason": "MISSING_DETAILS", "points": [], "payoff_month": None}
    monthly_rate = annual_rate / 100 / 12
    if balance * monthly_rate >= payment:
        return {"available": False, "reason": "PAYMENT_TOO_LOW", "points": [], "payoff_month": None,
                "monthly_interest": to_money(balance * monthly_rate)}
    points = [{"month": start_month, "balance": to_money(balance)}]
    each = start_month
    total_interest = 0
    while balance > 0.005 and len(points) <= MAX_LOAN_MONTHS:
        interest = balance * monthly_rate
        total_interest += interest
        balance = max(balance + interest - payment, 0)
        year, number = (int(part) for part in each.split("-"))
        each = f"{year + number // 12}-{number % 12 + 1:02d}"
        points.append({"month": each, "balance": to_money(balance)})
    paid_off = balance <= 0.005
    return {"available": True, "points": points, "payoff_month": points[-1]["month"] if paid_off else None,
            "months_left": len(points) - 1 if paid_off else None, "total_interest": to_money(total_interest)}


def build_loans(loans, loans_state, month):
    """One projection per saved loan + the combined outstanding balance. Repayment history isn't stored in the
    app, so only the projection from today is shown (history: null)."""
    if not loans:
        return {"available": False, "state": loans_state, "loans": [], "total": None}
    items = []
    for loan in loans:
        plan = project_loan(loan["balance"], loan["annual_rate"], loan["monthly_payment"], month)
        items.append({"id": loan["id"], "name": loan["name"], "balance": loan["balance"],
                      "annual_rate": loan["annual_rate"], "monthly_payment": loan["monthly_payment"],
                      "history": None, **plan})
    total = None
    if all(item["available"] for item in items):  # a combined line only when every loan can be projected
        length = max(len(item["points"]) for item in items)
        total = []
        for index in range(length):
            amount = sum(item["points"][index]["balance"] if index < len(item["points"]) else 0 for item in items)
            longest = max(items, key=lambda item: len(item["points"]))
            total.append({"month": longest["points"][index]["month"], "balance": to_money(amount)})
    return {"available": True, "state": loans_state, "loans": items, "total": total,
            "outstanding": to_money(sum(loan["balance"] for loan in loans)),
            "monthly_payments": get_total([{"amount": loan["monthly_payment"]} for loan in loans])}


# ===== 5. MONTHLY RECAP (fixed sentence templates; the frontend translates the codes) =====
def get_biggest_category(expenses, month):
    totals = {}
    for row in get_expenses_in_month(expenses, month):
        totals[row["category"]] = totals.get(row["category"], 0) + row["amount"]
    if not totals:
        return None
    category = max(sorted(totals), key=lambda name: totals[name])  # sorted: same answer every time on a tie
    return {"category": category, "amount": to_money(totals[category])}


def build_recap(records, choices, month, balance):
    status = get_month_status(records, choices, month)
    previous_month = get_previous_month(month)
    previous_status = get_month_status(records, choices, previous_month)
    expenses = records["expenses"]
    spent = get_total_spent(expenses, month) if is_known(status["expenses"]) else None
    saved = get_saved_in_month(records["deposits"], month)
    saved = saved if saved > 0 or is_known(status["savings"]) else None
    target = get_monthly_target(records["savings_row"]["monthly_target"] if records["savings_row"] else None,
                                records["incomes"], month)
    biggest = get_biggest_category(expenses, month) if status["expenses"] == "provided" else None
    recap = {
        "month": month,
        "income": get_monthly_income(records["incomes"], month) if is_known(status["income"]) else None,
        "expenses": spent,
        "savings": saved,
        "loan_repayments": get_loan_payments(records["loans"], month) if is_known(status["loans"]) else None,
        "remaining": balance["balance"] if balance["available"] else None,
        "biggest_category": biggest,
        "savings_progress": {"saved": saved, "target": target,
                             "percent": min(get_percent(saved, target), 100.0) if saved is not None and target else None},
        "statements": [],
    }
    statements = recap["statements"]
    previous_spent = get_total_spent(expenses, previous_month) if previous_status["expenses"] == "provided" else None
    has_history = previous_spent is not None and status["expenses"] == "provided"
    if has_history:
        change = change_percent(previous_spent, spent)
        if change is not None and abs(change) >= 5:
            statements.append({"code": "SPENDING_UP" if change > 0 else "SPENDING_DOWN",
                               "params": {"percent": round(abs(change))}})
        elif change is not None:
            statements.append({"code": "SPENDING_SAME", "params": {}})
        recap["previous_expenses"] = previous_spent
        recap["expenses_change_percent"] = change
    if biggest:
        before = get_biggest_category(expenses, previous_month) if has_history else None
        same = before is not None and before["category"] == biggest["category"]
        statements.append({"code": "TOP_CATEGORY_SAME" if same else "TOP_CATEGORY",
                           "params": {"category": biggest["category"], "amount": biggest["amount"]}})
    previous_saved = get_saved_in_month(records["deposits"], previous_month)
    if saved is not None and (previous_saved > 0 or saved > 0) and get_first_savings_month(
            records["deposits"], records["goals"]) not in (None, month):
        if saved > previous_saved:
            statements.append({"code": "SAVINGS_UP", "params": {"amount": to_money(saved - previous_saved)}})
        elif saved < previous_saved:
            statements.append({"code": "SAVINGS_DOWN", "params": {"amount": to_money(previous_saved - saved)}})
    if not has_history and spent is not None and status["expenses"] == "provided":
        count = len(get_expenses_in_month(expenses, month))
        statements.append({"code": "MONTH_SO_FAR", "params": {"count": count, "amount": spent}})
    if balance["available"]:
        statements.append({"code": "LEFT_POSITIVE" if balance["balance"] >= 0 else "LEFT_NEGATIVE",
                           "params": {"amount": abs(balance["balance"])}})
    return recap


# ===== 6. FINANCIAL HEALTH SCORE (0-100, habits, not wealth) =====
# Each part has a few checks. A check that can't be measured (missing information) is SKIPPED, not scored 0;
# the score is the points earned out of the points that could be measured. Under 50 measurable points → no score.
def check(code, points, maximum):
    return {"code": code, "points": round(points, 1), "max": maximum}


def score_budget(status, income, spent, saved, loans, category_rows):
    if status["income"] != "provided" or status["expenses"] != "provided":
        return [], "NEED_INCOME_AND_EXPENSES"
    outgoings = spent + (loans or 0)
    checks = [check("WITHIN_INCOME", 12 if outgoings <= income else 4 if outgoings <= income * 1.1 else 0, 12),
              check("POSITIVE_BALANCE", 8 if income - spent - saved - (loans or 0) >= 0 else 0, 8)]
    budgeted = [row for row in category_rows if row["budget"]]
    if budgeted:
        kept = sum(1 for row in budgeted if row["over_by"] == 0)
        checks.append(check("BUDGETS_KEPT", 10 * kept / len(budgeted), 10))
    return checks, None


def score_spending(status, income, expenses, month):
    if status["expenses"] != "provided":
        return [], "NEED_EXPENSES"
    rows = get_expenses_in_month(expenses, month)
    total = get_total(rows)
    wants = get_total_by_kind(expenses, month, "want")
    checks = []
    if status["income"] == "provided" and income > 0:  # wants vs income (needs are never penalised)
        share = wants / income * 100
        checks.append(check("WANTS_BALANCE", 10 if share <= 30 else 6 if share <= 40 else 2, 10))
    elif total > 0:
        share = wants / total * 100
        checks.append(check("WANTS_BALANCE", 10 if share <= 40 else 6 if share <= 60 else 2, 10))
    earlier = [get_total_spent(expenses, m) for m in get_recent_months(get_previous_month(month), 3)
               if get_expenses_in_month(expenses, m)]
    if earlier:
        average = sum(earlier) / len(earlier)
        rise = (total - average) / average * 100 if average > 0 else 0
        checks.append(check("STABLE_SPENDING", 10 if rise <= 15 else 6 if rise <= 30 else 3, 10))
    if rows:
        sorted_share = sum(1 for row in rows if row["category"] != "Other") / len(rows)
        checks.append(check("CATEGORISED", 5 if sorted_share >= 0.8 else 3 if sorted_share >= 0.5 else 1, 5))
    return checks, None


def score_savings(status, records, month, goal_rows):
    if status["savings"] != "provided":
        return [], "NEED_SAVINGS"
    deposits = records["deposits"]
    first = get_first_savings_month(deposits, records["goals"])
    checks = [check("SAVED_THIS_MONTH", 10 if get_saved_in_month(deposits, month) > 0 else 0, 10)]
    months = [m for m in get_recent_months(month, 3) if first is not None and m >= first]
    if len(months) >= 2:  # consistency needs at least 2 months since saving started
        share = sum(1 for m in months if get_saved_in_month(deposits, m) > 0) / len(months)
        checks.append(check("REGULAR_SAVING", 10 * share, 10))
    judged = [goal for goal in goal_rows if goal["status"] in ("On track", "Needs more", "Done")]
    if judged:
        share = sum(1 for goal in judged if goal["status"] in ("On track", "Done")) / len(judged)
        checks.append(check("GOALS_ON_TRACK", 5 * share, 5))
    return checks, None


def score_commitments(status, income, spent, loans):
    if not is_known(status["loans"]):
        return [], "NEED_LOANS"
    if status["loans"] == "none":
        return [check("NO_LOANS", 20, 20)], None
    # Repayment history isn't stored, so "paid on time" is never judged (never assumed missed)
    if status["income"] != "provided" or income <= 0:
        return [], "NEED_INCOME"
    share = loans / income * 100
    checks = [check("REPAYMENTS_FIT", 10 if share <= 30 else 6 if share <= 40 else 2, 10)]
    if status["expenses"] == "provided":
        checks.append(check("COMMITMENTS_COVERED", 10 if income - spent - loans >= 0 else 0, 10))
    return checks, None


PARTS = (("budget", 30), ("spending", 25), ("savings", 25), ("commitments", 20))
LEVELS = ((80, "excellent"), (60, "good"), (40, "fair"), (0, "needs_attention"))


def build_health_score(records, choices, month, category_rows, goal_rows):
    status = get_month_status(records, choices, month)
    income = get_monthly_income(records["incomes"], month)
    spent = get_total_spent(records["expenses"], month)
    saved = get_saved_in_month(records["deposits"], month)
    loans = get_loan_payments(records["loans"], month) if status["loans"] == "provided" else 0
    results = {
        "budget": score_budget(status, income, spent, saved, loans, category_rows),
        "spending": score_spending(status, income, records["expenses"], month),
        "savings": score_savings(status, records, month, goal_rows),
        "commitments": score_commitments(status, income, spent, loans),
    }
    parts = []
    measured_weight = 0
    earned_weight = 0
    for name, weight in PARTS:
        checks, reason = results[name]
        possible = sum(item["max"] for item in checks)
        got = sum(item["points"] for item in checks)
        # A part is scaled to its weight from the checks that could be measured
        points = round(got / possible * weight, 1) if possible else None
        if points is not None:
            measured_weight += weight
            earned_weight += points
        parts.append({"part": name, "weight": weight, "points": points, "checks": checks, "skipped_reason": reason})
    if measured_weight < SCORE_MIN_WEIGHT:
        return {"available": False, "reason": "NOT_ENOUGH_DATA", "parts": parts, "measured_weight": measured_weight}
    score = round(earned_weight / measured_weight * 100)
    level = next(name for limit, name in LEVELS if score >= limit)
    all_checks = [item for part in parts for item in part["checks"]]
    best = max(all_checks, key=lambda item: (item["points"] / item["max"], item["max"]))
    weakest = min(all_checks, key=lambda item: (item["points"] / item["max"], -item["max"]))
    return {"available": True, "score": score, "level": level, "parts": parts, "measured_weight": measured_weight,
            "strength": best["code"],
            "improve": weakest["code"] if weakest["points"] < weakest["max"] else None}


# ===== 7. WEEKLY BUDGET + BADGES =====
def get_week_start(day):
    """Monday of the week of `day` (weeks run Monday-Sunday in the user's local dates)."""
    return day - timedelta(days=day.weekday())


def get_week_spending(expenses, week_start):
    """Everyday expenses (not monthly fixed bills) dated Monday-Sunday of that week."""
    end = week_start + timedelta(days=6)
    rows = [e for e in expenses if not e["is_fixed"] and week_start.isoformat() <= e["date"] <= end.isoformat()]
    return {"total": get_total(rows), "days_recorded": len({row["date"] for row in rows})}


def get_finished_weeks(expenses, weekly_budget, today):
    """Every finished week since the budget was set, with its result. A week only counts as kept when spending was
    recorded on at least MIN_TRACKED_DAYS different days: an empty week is not proof of staying within budget."""
    if weekly_budget is None:
        return []
    set_on = date.fromisoformat(weekly_budget["set_on"])
    week = get_week_start(set_on)
    if set_on.weekday() != 0:
        week += timedelta(days=7)  # set mid-week → the first full week after
    weeks = []
    while week + timedelta(days=6) < today:
        spending = get_week_spending(expenses, week)
        tracked = spending["days_recorded"] >= MIN_TRACKED_DAYS
        weeks.append({"week_start": week.isoformat(), "week_end": (week + timedelta(days=6)).isoformat(),
                      "spent": spending["total"], "days_recorded": spending["days_recorded"],
                      "tracked": tracked, "kept": tracked and spending["total"] <= weekly_budget["amount"]})
        week += timedelta(days=7)
    return weeks


def get_saving_weeks(deposits, today, count=4):
    """True for each finished week (newest last) that had a deposit: the 'Savings Streak' needs 4 in a row."""
    weeks = []
    week = get_week_start(today) - timedelta(days=7)
    first = min((date.fromisoformat(d["date"]) for d in deposits), default=None)
    if first is None:
        return []
    while week + timedelta(days=6) >= first:
        end = week + timedelta(days=6)
        weeks.insert(0, {"week_end": end.isoformat(),
                         "saved": any(week.isoformat() <= d["date"] <= end.isoformat() for d in deposits)})
        week -= timedelta(days=7)
    return weeks


def find_new_badges(weeks, saving_weeks, already):
    """Badge code → date earned (the Sunday that completed it). Badges already earned are never given again,
    and earned badges are never taken away (even if old expenses are edited later)."""
    found = {}
    kept_weeks = [week for week in weeks if week["kept"]]
    if kept_weeks:
        found["FIRST_WEEK"] = kept_weeks[0]["week_end"]
    for earlier, later in zip(weeks, weeks[1:]):
        if earlier["kept"] and later["kept"]:
            found["BUDGET_KEEPER"] = later["week_end"]
            break
    if len(kept_weeks) >= 4:
        found["CONSISTENT_PLANNER"] = kept_weeks[3]["week_end"]
    run = 0
    for week in saving_weeks:
        run = run + 1 if week["saved"] else 0
        if run == 4:
            found["SAVINGS_STREAK"] = week["week_end"]
            break
    return {code: day for code, day in found.items() if code not in already}


def build_weekly(expenses, weekly_budget, today):
    if weekly_budget is None:
        return {"available": False, "budget": None}
    week = get_week_start(today)
    spending = get_week_spending(expenses, week)
    budget = weekly_budget["amount"]
    return {"available": True, "budget": budget, "week_start": week.isoformat(),
            "week_end": (week + timedelta(days=6)).isoformat(), "spent": spending["total"],
            "left": to_money(budget - spending["total"]), "days_recorded": spending["days_recorded"],
            "days_left": 6 - today.weekday(), "percent": get_percent(spending["total"], budget),
            "state": "over" if spending["total"] > budget else "on_track", "min_tracked_days": MIN_TRACKED_DAYS}


# ===== 8. SAVINGS JAR =====
def build_jar(goals, monthly_target, today):
    """One entry per goal: saved, target, remaining and % (the coins are drawn from the percent)."""
    rows = []
    for goal in get_goal_statuses(goals, monthly_target, today.isoformat()):
        rows.append({"id": goal["id"], "name": goal["name"], "saved": goal["saved_amount"],
                     "target": goal["target_amount"],
                     "remaining": to_money(max(goal["target_amount"] - goal["saved_amount"], 0)),
                     "percent": goal["percent"], "status": goal["status"]})
    return {"available": bool(rows), "goals": rows}


# ===== EVERYTHING =====
def build_dashboard(records, choices, savings_values, budgets, weekly_budget, earned_badges, today):
    """records = {incomes, expenses, deposits, goals, loans, savings_row}; today = a date (user's local day)."""
    month = today.isoformat()[:7]
    status = get_month_status(records, choices, month)
    monthly_target = get_monthly_target(savings_values["monthly_target"], records["incomes"], month)
    goal_rows = get_goal_statuses(records["goals"], monthly_target, today.isoformat())
    category_rows = get_category_spending(records["expenses"], budgets, month)
    balance = build_balance(records, choices, month, savings_values)
    weeks = get_finished_weeks(records["expenses"], weekly_budget, today)
    new_badges = find_new_badges(weeks, get_saving_weeks(records["deposits"], today), set(earned_badges))
    return {
        "today": today.isoformat(),
        "month": month,
        "info": status,
        "is_new_user": not any(records[key] for key in ("incomes", "expenses", "deposits", "goals", "loans")),
        "balance": balance,
        "spending": build_spending_series(records["expenses"], month),
        "savings": build_savings_series(records, choices, month),
        "loans": build_loans(records["loans"], status["loans"], month),
        "recap": build_recap(records, choices, month, balance),
        "health": build_health_score(records, choices, month, category_rows, goal_rows),
        "weekly": build_weekly(records["expenses"], weekly_budget, today),
        "recent_weeks": weeks[-4:],
        "new_badges": new_badges,  # saved by the route, then listed with the others
        "jar": build_jar(records["goals"], monthly_target, today),
    }
