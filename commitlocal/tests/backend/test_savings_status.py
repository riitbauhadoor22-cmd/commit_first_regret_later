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
    assert get_savings_status("provided", 2000, 2000, left=0)["code"] == "ON_TARGET"  # exactly used up: still fine


def test_no_well_done_when_left_to_spend_is_negative():  # spending + savings > income → gentle warning instead
    for target in (2000, 500, None):
        assert get_savings_status("provided", 2000, target, left=-150)["code"] == "OVER_INCOME"
    assert get_savings_status("provided", 0, 2000, left=-150)["code"] == "NONE_YET"  # nothing saved: not about savings


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


def summary_of(client):
    return client.get("/api/summary").json()


def test_left_to_spend_ignores_money_already_had(logged_in):  # old savings never make Left to spend negative
    month = get_this_month()
    logged_in.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 10000, "frequency": "monthly",
                                        "date": month + "-01"})
    logged_in.post("/api/expenses", json={"amount": 4000, "category": "Groceries"})
    logged_in.post("/api/savings/entries", json={"kind": "deposit", "amount": 50000, "place": "general",
                                                 "source": "already_had"})
    data = summary_of(logged_in)
    assert data["saved"] == 0 and data["left_to_spend"] == 6000 and data["left_reason"] is None


def test_money_card_warns_when_savings_and_spending_beat_income(logged_in):
    month = get_this_month()
    logged_in.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 10000, "frequency": "monthly",
                                        "date": month + "-01"})
    logged_in.post("/api/expenses", json={"amount": 9000, "category": "Groceries"})
    logged_in.post("/api/savings/entries", json={"kind": "deposit", "amount": 2000, "place": "general"})
    data = summary_of(logged_in)  # saved 2,000 = the 20% target, but 10,000 − 9,000 − 2,000 = −1,000
    assert data["left_to_spend"] == -1000 and data["left_reason"] == "SAVING_AND_SPENDING"
    assert data["savings_status"]["code"] == "OVER_INCOME"

