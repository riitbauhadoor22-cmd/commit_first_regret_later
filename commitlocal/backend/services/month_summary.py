# services/month_summary.py — THE one place that works out a month's In, Out, Saved, Left to spend, the 50/30/20
# split and the spending forecast. /api/summary, /api/savings, /api/forecast, the Dashboard and Financial insights all
# call build_month_summary, so every page shows the same numbers. Plain maths, no database (easy to test).
#
# Three savings values — never mixed:
#   bank_savings_balance  = money ALREADY in the bank (Money → Savings → "Update"). A balance, not a monthly flow:
#                           it is never part of In, Out, Saved, Left to spend, the split or the forecast.
#   monthly_saving_target = what the user plans to save each month ("Change"), or 20% of regular income.
#   saved_this_month      = REAL money: "Add to savings" − "Take out" entries dated this month (deposits table,
#                           any place: general, safety net or a goal). The target is only the goal it's compared with.
from money import (get_fixed_bills, get_monthly_income, get_monthly_target, get_month_of, get_percent,
                   get_saved_in_month, get_total, get_total_by_kind, get_total_spent, to_money)
from services.forecast import build_spending_forecast

KNOWN = ("provided", "none")  # same rule as info_status.is_known


# ===== LOANS =====
def loan_counts_in_month(loan, month):
    """A saved loan's repayment counts from its start month (or the month it was saved) onwards."""
    start = loan["start_date"] or loan["created_at"][:10]
    return get_month_of(start) <= month


def get_loan_payments(loans, month):
    return get_total([{"amount": loan["monthly_payment"]} for loan in loans if loan_counts_in_month(loan, month)])


def get_loans_not_in_bills(loans, fixed_bills, month):
    """Saved loan repayments that are NOT already recorded as a fixed bill. Many users also add their loan as a fixed
    monthly bill; a saved loan whose monthly_payment equals a fixed bill's amount is treated as that same bill and is
    left out (each fixed bill can only match one loan), so it is never taken off twice."""
    unmatched_bills = [bill["amount"] for bill in fixed_bills]
    total = 0
    for loan in loans:
        if not loan_counts_in_month(loan, month):
            continue
        if loan["monthly_payment"] in unmatched_bills:
            unmatched_bills.remove(loan["monthly_payment"])  # already counted in the fixed bills
            continue
        total += loan["monthly_payment"]
    return to_money(total)


# ===== SAVINGS =====
def get_saved_this_month(savings_state, deposits, month):
    """saved_this_month: savings never mentioned → None (shown "—") · otherwise money put into savings − money
    taken out this month (0 when nothing was added, also for "I'm not saving right now")."""
    if savings_state == "missing":
        return None
    return get_saved_in_month(deposits, month)


def get_saving_progress(saved, target):
    """Monthly saving card: percent (bar, never above 100), reached, extra above the target.
    No target (None or 0) → "no_target", so the screen asks the user to set one (never ÷ 0)."""
    if not target or target <= 0:
        return {"state": "no_target", "percent": 0.0, "reached": False, "extra": 0.0}
    saved = saved or 0
    return {"state": "ok", "percent": min(get_percent(saved, target), 100.0), "reached": saved >= target,
            "extra": to_money(max(saved - target, 0))}


def get_savings_status(savings_state, saved, target):
    """Which encouraging savings message to show (never blaming): {"code", "saved", "target"}.
    NOT_TRACKED = savings never added (not counted as off plan) · NONE_YET = "I'm not saving" or nothing saved yet ·
    BELOW_TARGET / ON_TARGET = compared with the monthly saving target · SAVED_NO_TARGET = saved, but no target."""
    if savings_state == "missing" or saved is None:
        code = "NOT_TRACKED"
    elif savings_state == "none" or saved <= 0:
        code = "NONE_YET"
    elif not target:
        code = "SAVED_NO_TARGET"
    else:
        code = "ON_TARGET" if saved >= target else "BELOW_TARGET"
    return {"code": code, "saved": saved, "target": target}


# ===== 50 / 30 / 20 SPLIT =====
def build_split(income, needs, wants, saved, loans):
    """Each part as a share of income + a grey "not planned yet" rest. "bar" widths always add up to 100 (squeezed
    when the parts are more than the income). None when there is no income: nothing to divide by."""
    if income is None or income <= 0 or needs is None or wants is None:
        return None
    parts = {"needs": needs, "wants": wants, "savings": saved or 0, "loans": loans or 0}
    used = sum(parts.values())
    scale = max(used, income)  # over income → the bar is as long as what's used, so it never goes past 100%
    bar = {name: round(amount / scale * 100, 2) for name, amount in parts.items()}
    bar["unplanned"] = round(max(100 - sum(bar.values()), 0), 2)
    percent = {name: get_percent(amount, income) for name, amount in parts.items()}
    percent["unplanned"] = get_percent(max(income - used, 0), income)
    return {"percent": percent, "bar": bar, "over_income": used > income}


# ===== THE MONTH SUMMARY =====
def build_month_summary(incomes, expenses, loans, savings_values, info, month, today=None, budgets=(), deposits=()):
    """In / Out / Saved / Left to spend / split (+ forecast when `today` is given) for one month.
    info = {"income", "expenses", "loans", "savings"}: provided / none / missing. Missing → None, never Rs 0.
    savings_values = {"monthly_target": own target or None, "bank_balance": ..., ...} (bank balance is NOT used here).
    deposits = the savings entries (deposits table): Saved = put in − taken out this month.
    Out = everyday + fixed bills + saved-loan repayments that aren't already a fixed bill (loans only when shared)."""
    info = {topic: info.get(topic, "provided") for topic in ("income", "expenses", "loans", "savings")}
    income = get_monthly_income(incomes, month) if info["income"] in KNOWN else None
    expenses_known = info["expenses"] in KNOWN
    spent = get_total_spent(expenses, month) if expenses_known else None
    needs = get_total_by_kind(expenses, month, "need") if expenses_known else None
    wants = get_total_by_kind(expenses, month, "want") if expenses_known else None
    fixed_bills = get_fixed_bills(expenses, month)
    loan_repayments = get_loans_not_in_bills(loans, fixed_bills, month) if info["loans"] in KNOWN else None
    out = to_money(spent + (loan_repayments or 0)) if spent is not None else None
    monthly_target = get_monthly_target(savings_values.get("monthly_target"), incomes, month)
    saved = get_saved_this_month(info["savings"], deposits, month)

    # Left to spend = In − Out − Saved (needs income AND spending; unknown saving = nothing planned)
    left = to_money(income - out - (saved or 0)) if income is not None and out is not None else None
    left_reason = None
    if left is not None and left < 0:
        left_reason = "SAVING_AND_SPENDING" if saved and saved > 0 else "SPENDING"

    split = build_split(income, needs, wants, max(saved or 0, 0), loan_repayments)  # more taken out than put in = 0
    summary = {
        "month": month,
        "info": info,
        "income": income,
        "spent": spent,                      # everyday + fixed bills (what the expense lists show)
        "loan_repayments": loan_repayments,  # None = loans not shared
        "out": out,                          # spent + loan repayments
        "needs": needs,
        "wants": wants,
        "saved": saved,                      # saved_this_month
        "monthly_target": monthly_target,
        "left_to_spend": left,
        "left_reason": left_reason,
        "needs_percent": split["percent"]["needs"] if split else None,
        "wants_percent": split["percent"]["wants"] if split else None,
        "savings_percent": split["percent"]["savings"] if split and saved is not None else None,
        "savings_status": get_savings_status(info["savings"], saved, monthly_target),
        "split": split,
    }
    if today is not None:
        summary["forecast"] = build_spending_forecast(
            incomes, expenses, list(budgets), saved or 0, today, month, loan_repayments or 0)
    return summary
