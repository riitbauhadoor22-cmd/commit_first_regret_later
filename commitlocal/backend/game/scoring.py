# game/scoring.py — scores a Budget Challenge allocation out of 100 and explains why (deterministic, server-only).
# Points: budget balance 30 · essential needs 25 · spending allocation (plain 50·30·20) 20 · savings 15 · events 10.
# Feedback = codes + numbers ({"code": "unassigned", "params": {"left": 1200}}); the frontend translates "game.tip.<code>".
from game.budget_engine import effective_income, group_totals, minimums
from game.scenarios import (BUFFER_PERCENT, GUIDE, POINTS, SAVINGS_GOAL_PERCENT, SAVINGS_SOME_POINTS, SPLIT_FULL_WITHIN,
                            SPLIT_HALF_WITHIN, SPLIT_SHARES)
from money import to_rupees


# ===== PARTS =====
def round_half_up(value):
    """Rounds .5 up (Python's round() would make 12.5 -> 12)."""
    return int(value + 0.5)


def balance_points(left_percent):
    """30 within income; 20 when more than 10% of income is left unallocated; 0 if over income."""
    if left_percent < 0:
        return 0
    return POINTS["balance"] if left_percent <= BUFFER_PERCENT else 20


def allocation_points(percents):
    """Each group vs plain 50·30·20: full share within ±10 points, half share within ±20, else 0.
    Shares: needs 7, wants 7, savings 6. Halves of 7 make x.5 totals: the total is rounded half up (16.5 -> 17)."""
    total = 0
    for kind, share in SPLIT_SHARES.items():
        gap = abs(percents[kind] - GUIDE[kind])
        total += share if gap <= SPLIT_FULL_WITHIN else share / 2 if gap <= SPLIT_HALF_WITHIN else 0
    return round_half_up(total)


def savings_points(saved, income):
    """0 if nothing saved; 10 if under 10% of income; 15 from 10% (no extra above 20%)."""
    if saved <= 0:
        return 0
    return POINTS["savings"] if saved * 100 >= income * SAVINGS_GOAL_PERCENT else SAVINGS_SOME_POINTS


# ===== SCORE =====
def score_allocation(level, cents, event=None, event_applied=True):
    """Score for one allocation ({category: cents}).
    event         → the attempt's event (None = events off)
    event_applied → False on the first (preview) submit: the event hasn't happened yet, its 10 points are pending."""
    active = event if event_applied else None
    income = effective_income(level, active)
    total = sum(cents.values())
    left = income - total
    groups = group_totals(level, cents)
    percents = {kind: value * 100 / income for kind, value in groups.items()}
    needed = minimums(level, active)      # essential minimums after the event (cost raises, discount lowers)
    # Coverage uses the scenario minimums (a discount may lower them); a missed cost event only costs the 10 event points
    # Only min_amount categories are essentials here: locked commitments (rent, loan) can't change, so they don't count
    essential_ids = {c["id"] for c in level["categories"] if "min_amount" in c}
    coverage = {cid: need for cid, need in minimums(level, active if active and active["type"] == "discount" else None).items()
                if cid in essential_ids}
    tips = []

    # 1) Budget balance (30)
    balance = balance_points(left * 100 / income)
    # 2) Essential needs coverage (25): share of essentials at or above their minimum
    short = [cid for cid, need in coverage.items() if cents[cid] < need]
    essentials = round_half_up(POINTS["essentials"] * (len(coverage) - len(short)) / len(coverage)) if coverage else POINTS["essentials"]
    # 3) Spending allocation awareness (20)
    allocation = allocation_points(percents)
    # 4) Savings planning (15): the Savings category as a % of income
    goal = income * SAVINGS_GOAL_PERCENT / 100
    saved = cents.get("savings", 0)
    savings = savings_points(saved, income)
    # 5) Handling unexpected events (10)
    if event is None:
        events = POINTS["events"]  # events off: automatic, so scores stay comparable
    elif not event_applied:
        events = None
    else:
        coped = left >= 0 and all(cents[cid] >= need for cid, need in needed.items())  # within income + raised minimums met
        events = POINTS["events"] if coped else 0

    # ===== FEEDBACK (explains the reasoning) =====
    if left >= 0 and not short:
        tips.append({"code": "balanced", "params": {}})
    if left < 0:
        tips.append({"code": "overspend", "params": {"over": to_rupees(-left)}})
    tips += [{"code": "essential_short", "params": {"category": cid, "min": to_rupees(coverage[cid])}} for cid in short]
    if short and saved > 0:
        tips.append({"code": "save_vs_essentials", "params": {}})
    if percents["need"] > GUIDE["need"]:
        realistic = percents["need"] <= GUIDE["need"] + SPLIT_FULL_WITHIN  # still full allocation points
        tips.append({"code": "high_needs_ok" if realistic else "needs_high", "params": {"n": round(percents["need"])}})
    if percents["want"] > GUIDE["want"] + 5:
        tips.append({"code": "large_wants", "params": {"n": round(percents["want"])}})
    if saved == 0:
        tips.append({"code": "no_savings", "params": {}})
    elif saved < goal:
        tips.append({"code": "savings_low", "params": {"target": to_rupees(round(goal))}})
    if left > 0:
        tips.append({"code": "unassigned", "params": {"left": to_rupees(left)}})
    if event is not None and event_applied:
        tips.append({"code": "event_handled" if events else "event_failed",
                     "params": {"category": event["category"], "amount": event["amount"]}})

    parts = {"balance": balance, "essentials": essentials, "allocation": allocation, "savings": savings, "events": events}
    score = sum(points for points in parts.values() if points is not None)
    if score == 100:
        tips.append({"code": "great", "params": {}})
    return {
        "score": score,
        "breakdown": [{"key": key, "points": points, "max": POINTS[key]} for key, points in parts.items()],
        "income": to_rupees(income), "total": to_rupees(total), "left": to_rupees(left),
        "totals": {kind: to_rupees(value) for kind, value in groups.items()},
        "percents": {kind: round(value, 1) for kind, value in percents.items()},
        "targets": dict(GUIDE),
        "tips": tips,
    }
