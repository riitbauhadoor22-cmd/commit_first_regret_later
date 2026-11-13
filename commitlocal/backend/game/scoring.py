# game/scoring.py — scores a Budget Challenge allocation out of 100 and explains why (deterministic, server-only).
# Points: budget balance 30 · essential needs 25 · spending allocation (50·30·20, scenario-aware) 20 · savings 15 · events 10.
# Feedback = codes + numbers ({"code": "unassigned", "params": {"left": 1200}}); the frontend translates "game.tip.<code>".
from game.budget_engine import effective_income, group_totals, minimums
from game.scenarios import (BUFFER_PERCENT, GUIDE, POINTS, SAVINGS_GOAL_PERCENT, SPLIT_FULL_WITHIN, SPLIT_ZERO_AT)
from money import to_rupees


# ===== PARTS =====
def balance_points(left_percent):
    """30 within income with ≤ 10% unallocated (a sensible buffer); 20 up to 25% unallocated; 10 above; 0 if over."""
    if left_percent < 0:
        return 0
    if left_percent <= BUFFER_PERCENT:
        return POINTS["balance"]
    return 20 if left_percent <= 25 else 10


def allocation_targets(level, needed, income):
    """50·30·20, but when this scenario's essential minimums already take more than 50%, Needs may be that high
    (the extra comes out of Wants) — high-rent levels aren't punished for being realistic."""
    kinds = {c["id"]: c["kind"] for c in level["categories"]}
    need_floor = sum(cents for cid, cents in needed.items() if kinds[cid] == "need") * 100 / income
    need = max(GUIDE["need"], need_floor)
    return {"need": need, "want": max(0, GUIDE["want"] - (need - GUIDE["need"])), "savings": GUIDE["savings"]}


def allocation_points(percents, targets):
    """20 when close to the targets (distance ≤ 10 points), 0 when ≥ 50 away; Needs above target only count half."""
    need_gap = percents["need"] - targets["need"]
    distance = (need_gap / 2 if need_gap > 0 else -need_gap) + abs(percents["want"] - targets["want"]) \
        + abs(percents["savings"] - targets["savings"])
    if distance <= SPLIT_FULL_WITHIN:
        return POINTS["allocation"]
    share = max(0.0, (SPLIT_ZERO_AT - distance) / (SPLIT_ZERO_AT - SPLIT_FULL_WITHIN))
    return round(POINTS["allocation"] * share)


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
    coverage = minimums(level, active if active and active["type"] == "discount" else None)
    targets = allocation_targets(level, needed, income)
    tips = []

    # 1) Budget balance (30)
    balance = balance_points(left * 100 / income)
    # 2) Essential needs coverage (25): share of essentials at or above their minimum
    short = [cid for cid, need in coverage.items() if cents[cid] < need]
    essentials = round(POINTS["essentials"] * (len(coverage) - len(short)) / len(coverage)) if coverage else POINTS["essentials"]
    # 3) Spending allocation awareness (20)
    allocation = allocation_points(percents, targets)
    # 4) Savings planning (15): Savings category up to 10% of income; no extra above, capped if essentials are short
    goal = income * SAVINGS_GOAL_PERCENT / 100
    saved = cents.get("savings", 0)
    savings = round(POINTS["savings"] * min(1.0, saved / goal))
    if short and saved > 0:
        savings = min(savings, 5)
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
        realistic = percents["need"] <= targets["need"] + 5
        tips.append({"code": "high_needs_ok" if realistic else "needs_high", "params": {"n": round(percents["need"])}})
    if percents["want"] > targets["want"] + 5:
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
        "targets": {kind: round(value, 1) for kind, value in targets.items()},
        "tips": tips,
    }
