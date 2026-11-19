# test_savings_status.py — the encouraging savings message (provided / none / missing) on the Money card and the
# plan: never added → "not tracked" (never off plan), "not saving" or 0 → "none yet", below / on target.
from budget_plans import PLANS
from money import get_this_month
from services.budget_plan import judge_month, plan_progress
from services.month_summary import get_savings_status


def test_status_codes():
    assert get_savings_status("missing", None, 2000)["code"] == "NOT_TRACKED"
    assert get_savings_status("none", 0, 2000)["code"] == "NONE_YET"
    assert get_savings_status("provided", 0, 2000)["code"] == "NONE_YET"
    assert get_savings_status("provided", -300, 2000)["code"] == "NONE_YET"  # more taken out than put in
    below = get_savings_status("provided", 500, 2000)
    assert below == {"code": "BELOW_TARGET", "saved": 500, "target": 2000}
    assert get_savings_status("provided", 2000, 2000)["code"] == "ON_TARGET"
    assert get_savings_status("provided", 500, None)["code"] == "SAVED_NO_TARGET"


def figures(state, saved, loans=0):
    return {"month": "2026-10", "income": 10000, "needs": 4000, "wants": 2000, "saved": saved, "loans": loans,
            "fixed_costs": 0, "wants_by_category": {}, "savings_state": state}


def test_not_tracked_savings_never_make_a_month_off_plan():
    result = judge_month(figures("missing", None), "fifty_thirty_twenty")
    assert result["status"] == "on_plan" and result["savings_short"] == 0
    assert result["details"]["savings_tracked"] is False
    assert plan_progress(figures("missing", None), "fifty_thirty_twenty")["savings"]["actual"] is None


def test_tracked_savings_are_compared_with_the_plan():
    assert judge_month(figures("none", 0), "fifty_thirty_twenty")["savings_short"] == 2000
    assert judge_month(figures("provided", 2000), "fifty_thirty_twenty")["status"] == "on_plan"


def test_debt_first_still_counts_loans_when_savings_are_not_tracked():
    assert PLANS["debt_focus"]["loans_in_savings"]
    result = judge_month(figures("missing", None, loans=500), "debt_focus")
    assert result["savings_short"] == 1500  # 20% = 2,000, loans paid 500


def test_money_card_messages(logged_in):
    month = get_this_month()
    status = lambda: logged_in.get("/api/summary").json()["savings_status"]  # noqa: E731
    assert status()["code"] == "NOT_TRACKED"
    assert logged_in.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 10000,
                                               "frequency": "monthly", "date": month + "-01"}).status_code == 201
    assert logged_in.put("/api/info-choices", json={"topic": "savings", "none": True}).status_code == 200
    assert status()["code"] == "NONE_YET"
    logged_in.post("/api/savings/entries", json={"kind": "deposit", "amount": 500, "place": "general"})
    assert status() == {"code": "BELOW_TARGET", "saved": 500, "target": 2000}  # target = 20% of income
    logged_in.post("/api/savings/entries", json={"kind": "deposit", "amount": 1500, "place": "general"})
    assert status()["code"] == "ON_TARGET"
    assert logged_in.get("/api/plan").json().get("savings_status") is None  # no plan yet: no plan card message
