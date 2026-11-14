# services/financial_analysis.py — the money check-up behind "Financial insights". NO AI here: plain maths.
# Works out needs / wants / savings against the 50/30/20 guide, goal progress and the change since last month,
# plus simple observations (codes the frontend translates). It also builds the SMALL anonymous summary that
# may be sent to Groq (no names, no notes), and a fingerprint of it so we know when a saved AI analysis is out of date.
# Information the user hasn't given ("missing") is None and left out, never treated as zero.
import hashlib
import json

from info_status import is_known
from money import (get_expenses_in_month, get_fixed_bills, get_goal_statuses, get_months_left,
                   get_percent, get_safety_net, get_total, get_total_spent,
                   to_money)
from services.month_summary import build_month_summary

# 50/30/20 is a GUIDE, not a rule: needs 50%, wants 30%, savings + debt repayments 20% of take-home income
TARGETS = {"needs": 50, "wants": 30, "savings_and_debt": 20}
NOTABLE_POINTS = 5        # a group counts as "above" / "below" the guide only when it is 5+ points away
NOTABLE_CHANGE = 10       # spending changes under 10% vs last month are not mentioned
TOP_CATEGORIES = 6
MAX_GOALS_SENT = 8        # keeps the AI input small
FINGERPRINT_STEP = 50     # money rounded to Rs 50 for the fingerprint: tiny edits don't make the analysis outdated


# ===== SMALL HELPERS =====
def get_previous_month(month):
    """'2026-01' -> '2025-12'"""
    year, number = (int(part) for part in month.split("-"))
    if number == 1:
        return f"{year - 1}-12"
    return f"{year}-{number - 1:02d}"


def get_category_totals(expenses, month):
    """This month's spending per category (fixed bills included), biggest first."""
    totals = {}
    for expense in get_expenses_in_month(expenses, month):
        row = totals.setdefault(expense["category"], {"category": expense["category"], "kind": expense["kind"],
                                                      "amount": 0})
        row["amount"] = to_money(row["amount"] + expense["amount"])
    return sorted(totals.values(), key=lambda row: row["amount"], reverse=True)[:TOP_CATEGORIES]


def get_spending_change(expenses, month):
    """Total spent this month vs last month. None when there is no spending recorded last month."""
    previous = get_previous_month(month)
    if not get_expenses_in_month(expenses, previous):
        return None
    before = get_total_spent(expenses, previous)
    now = get_total_spent(expenses, month)
    change = round((now - before) / before * 100, 1) if before > 0 else None
    return {"previous_month": previous, "previous_total": before, "current_total": now, "change_percent": change}


def make_split_row(group, amount, income, complete=True):
    """One line of the 50/30/20 table. amount None = unknown. Percent needs a known amount and an income above 0.
    The difference from the guide is only given when the group is complete (e.g. loans known for savings & debt)."""
    percent = get_percent(amount, income) if amount is not None and income is not None and income > 0 else None
    difference = round(percent - TARGETS[group], 1) if percent is not None and complete else None
    return {"group": group, "amount": to_money(amount) if amount is not None else None, "percent": percent,
            "target_percent": TARGETS[group], "difference_points": difference, "complete": complete}


def get_goal_progress(goals, monthly_target, today):
    """Each goal with % saved, what it needs a month and its status (same rules as the Targets tab)."""
    rows = []
    for goal in get_goal_statuses(goals, monthly_target, today):
        rows.append({"name": goal["name"], "category": goal["category"], "target": goal["target_amount"],
                     "saved": goal["saved_amount"], "percent": goal["percent"],
                     "needs_per_month": goal["needs_per_month"], "plan": goal["plan"],
                     "months_left": get_months_left(today, goal["deadline"]) if goal["plan"] == "ok" else None,
                     "status": goal["status"], "priority": goal["priority_name"]})
    return rows


def add_or_none(*values):
    """Sum of the known values; None if none of them is known."""
    known = [value for value in values if value is not None]
    return to_money(sum(known)) if known else None


# ===== OBSERVATIONS (no AI: codes + numbers, the frontend shows them in the user's language) =====
def build_observations(analysis):
    """Only notes we can back with numbers the user gave. Unknown topics are listed in data_gaps instead."""
    notes = []
    income = analysis["take_home_income"]
    split = {row["group"]: row for row in analysis["split"]}
    if income is not None and income > 0:
        if analysis["remaining"] is not None and analysis["remaining"] < 0:
            notes.append({"code": "OVER_INCOME", "params": {"amount": to_money(-analysis["remaining"])}})
        differences = {group: row["difference_points"] for group, row in split.items()}
        if differences["needs"] is not None and differences["needs"] >= NOTABLE_POINTS:
            notes.append({"code": "NEEDS_ABOVE", "params": {"points": round(differences["needs"])}})
        if differences["wants"] is not None and differences["wants"] >= NOTABLE_POINTS:
            notes.append({"code": "WANTS_ABOVE", "params": {"points": round(differences["wants"])}})
        savings_gap = differences["savings_and_debt"]
        if savings_gap is not None and savings_gap <= -NOTABLE_POINTS:
            notes.append({"code": "SAVINGS_BELOW", "params": {"points": round(-savings_gap)}})
        if not notes and None not in differences.values():
            notes.append({"code": "WITHIN_GUIDE", "params": {}})
    change = analysis["spending_change"]
    if change and change["change_percent"] is not None and abs(change["change_percent"]) >= NOTABLE_CHANGE:
        code = "SPENDING_UP" if change["change_percent"] > 0 else "SPENDING_DOWN"
        notes.append({"code": code, "params": {"percent": round(abs(change["change_percent"]))}})
    behind = [goal for goal in analysis["goals"] if goal["status"] == "Needs more"]
    if behind:
        notes.append({"code": "GOALS_BEHIND", "params": {"count": len(behind)}})
    return notes


def get_data_gaps(info, goals, spending_change):
    """What the user hasn't told us (state "missing"). Shown as friendly prompts and told to the AI, never guessed."""
    gaps = [code for topic, code in (("income", "NO_INCOME"), ("expenses", "NO_EXPENSES"), ("loans", "NO_LOANS"),
                                     ("savings", "NO_SAVINGS")) if not is_known(info[topic])]
    if info["savings"] != "missing" and not goals:
        gaps.append("NO_GOALS")
    if info["expenses"] == "provided" and spending_change is None:
        gaps.append("NO_HISTORY")
    return gaps


# ===== THE WHOLE CHECK-UP =====
def analyse_month(incomes, expenses, deposits, goals, savings, loans, info, month, today):
    """Everything the insights card shows, worked out without AI.
    info = {"income", "expenses", "loans", "savings"}: provided / none / missing (info_status.py).
    Missing -> None (unknown), never 0. "none" (the user said so) -> 0.
    Income entries are treated as take-home (money that actually reaches you). In, Out, Savings (saved_this_month)
    and remaining come from the SAME shared function as the Money tab (services/month_summary.py); loans = saved
    loan repayments not already recorded as a fixed bill, so nothing is counted twice. The bank balance is money
    already saved: it is never part of this month's numbers."""
    flows = build_month_summary(incomes, expenses, loans, savings, info, month)
    income = flows["income"]
    expenses_known = is_known(info["expenses"])
    needs, wants = flows["needs"], flows["wants"]
    saved = flows["saved"]
    loan_payments = flows["loan_repayments"]
    remaining = flows["left_to_spend"]
    monthly_target = flows["monthly_target"]
    spending_change = get_spending_change(expenses, month) if info["expenses"] == "provided" else None
    analysis = {
        "month": month,
        "info": info,
        "take_home_income": income,
        "needs": needs,
        "wants": wants,
        "savings": saved,  # saved_this_month (the planned monthly saving)
        "bank_savings_balance": savings.get("bank_balance"),  # money already saved (None = not added)
        "loan_repayments": loan_payments,
        "remaining": remaining,
        "remaining_excludes_loans": remaining is not None and loan_payments is None,
        "split": [make_split_row("needs", needs, income), make_split_row("wants", wants, income),
                  make_split_row("savings_and_debt", add_or_none(saved, loan_payments), income,
                                 complete=saved is not None and loan_payments is not None)],
        "categories": get_category_totals(expenses, month) if expenses_known else [],
        "fixed_bills_total": get_total(get_fixed_bills(expenses, month)) if expenses_known else None,
        "spending_change": spending_change,
        "goals": get_goal_progress(goals, monthly_target, today),
        "monthly_saving_target": monthly_target,
        "safety_net": get_safety_net(expenses, savings["safety_net_saved"], month) if expenses_known else None,
        "data_gaps": get_data_gaps(info, goals, spending_change),
        # The AI is only offered when at least one topic has real records (otherwise there's nothing to explain)
        "enough_for_ai": "provided" in info.values(),
    }
    analysis["observations"] = build_observations(analysis)
    return analysis


# ===== QUICK INSIGHTS (no AI: used when Groq isn't set up or fails) =====
MAX_QUICK_GOALS = 3


def build_quick_insights(analysis):
    """Short rule-based tips from the user's own numbers: 50/30/20 comparison, biggest spending category,
    savings goal progress and loan repayment share. Codes + numbers; the frontend translates them (insights.quick.*).
    Unknown topics give an "add it" tip instead of a guess."""
    tips = []
    income = analysis["take_home_income"]
    if income is None or income <= 0:
        tips.append({"code": "ADD_INCOME", "params": {}})
    else:
        for row in analysis["split"]:
            if row["percent"] is not None:
                tips.append({"code": "SPLIT", "params": {"group": row["group"], "percent": round(row["percent"]),
                                                         "aim": row["target_percent"]}})
    categories = analysis["categories"]
    if categories:
        spent = sum(row["amount"] for row in categories) or 1  # top categories' total (never ÷ 0)
        top = categories[0]
        tips.append({"code": "TOP_CATEGORY", "params": {"category": top["category"], "amount": top["amount"],
                                                        "percent": round(top["amount"] / spent * 100)}})
    elif analysis["needs"] is None:
        tips.append({"code": "ADD_EXPENSES", "params": {}})
    for goal in analysis["goals"][:MAX_QUICK_GOALS]:
        if goal["status"] == "Done":
            code = "GOAL_DONE"
        elif goal["plan"] == "ok":
            code = "GOAL_PLAN"
        else:
            code = "GOAL_LATE" if goal["plan"] == "deadline_passed" else "GOAL_NO_PLAN"
        tips.append({"code": code, "params": {"name": goal["name"], "percent": round(goal["percent"]),
                                              "amount": goal["needs_per_month"]}})
    loans = analysis["loan_repayments"]
    if loans:
        if income:
            tips.append({"code": "LOAN_SHARE", "params": {"amount": loans, "percent": round(loans / income * 100)}})
        else:
            tips.append({"code": "LOAN_AMOUNT", "params": {"amount": loans}})
    return tips


# ===== WHAT MAY BE SENT TO GROQ (compact, anonymous, only what the user gave) =====
def build_ai_summary(analysis):
    """Only calculated figures the user actually gave: no goal names, notes, email or ids (goals = "Goal 1"...).
    Unknown topics are LEFT OUT and listed in missing_information, so the AI can't read them as zero."""
    summary = {"period": analysis["month"], "currency": "Mauritian rupees (Rs)",
               "information_given": analysis["info"]}  # provided / none (user said: nothing) / missing (unknown)
    optional = {
        "take_home_income": analysis["take_home_income"],
        "needs": analysis["needs"],
        "wants": analysis["wants"],
        "saved_this_month": analysis["savings"],  # planned monthly saving, part of this month's money
        "bank_savings_balance": analysis.get("bank_savings_balance"),  # already saved, NOT this month's money
        "loan_repayments": analysis["loan_repayments"],
        "remaining": analysis["remaining"],
        "fixed_bills_total": analysis["fixed_bills_total"],
        "spending_change": analysis["spending_change"],
        "monthly_saving_target": analysis["monthly_saving_target"],
        "safety_net": analysis["safety_net"],
    }
    summary.update({key: value for key, value in optional.items() if value is not None})
    if analysis["remaining_excludes_loans"]:
        summary["remaining_note"] = "remaining does not include loan repayments (unknown)"
    split = [{key: row[key] for key in ("group", "percent", "target_percent", "difference_points")}
             for row in analysis["split"] if row["percent"] is not None]
    if split:
        summary["split_vs_50_30_20"] = split
    if analysis["categories"]:
        summary["top_categories"] = analysis["categories"]
    goals = [{"label": f"Goal {number}", "category": goal["category"] or "General", "target": goal["target"],
              "saved": goal["saved"], "percent": goal["percent"], "needs_per_month": goal["needs_per_month"],
              "months_left": goal["months_left"], "plan": goal["plan"], "status": goal["status"], "priority": goal["priority"]}
             for number, goal in enumerate(analysis["goals"][:MAX_GOALS_SENT], start=1)]
    if goals:
        summary["goals"] = goals
    summary["missing_information"] = analysis["data_gaps"]
    return summary


def coarsen(value, key=""):
    """Rounds the numbers for the fingerprint: percents to whole numbers, money to Rs 50."""
    if isinstance(value, dict):
        return {k: coarsen(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [coarsen(item, key) for item in value]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if "percent" in key or key in ("difference_points", "months_left"):
        return round(value)
    return round(value / FINGERPRINT_STEP) * FINGERPRINT_STEP


def get_fingerprint(summary):
    """A short hash of the (rounded) summary. Same numbers → same fingerprint → the saved analysis is still valid."""
    text = json.dumps(coarsen(summary), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
