# test_budget_plan.py — budget plans: starting plan, weekly → monthly, the monthly recommendation and its
# thresholds, the commitment rules (next-month changes, one change a month, friction for looser plans, past months
# never rewritten), streaks and that one user never sees another's plan. Dates are moved with DEMO_TODAY.
import pytest

from budget_plans import PLANS, is_looser
from conftest import log_in
from services.budget_plan import (build_recommendation, count_streak, has_enough_data, judge_month,
                                  suggest_start_plan, switch_cost)

PLAN = "/api/plan"
START = {"life": "working", "pays_rent": False, "has_loan": False, "irregular_income": False}


# ===== HELPERS =====
def month(name, income=10000, fixed=2000, loans=0, saved=2000, wants=2000, needs=4000, wants_by_category=None):
    return {"month": name, "income": income, "fixed_costs": fixed + loans, "loans": loans, "saved": saved,
            "wants": wants, "needs": needs, "wants_by_category": wants_by_category or {"Shopping": wants}}


def at(monkeypatch, day):
    monkeypatch.setenv("DEMO_TODAY", day)


def start(client, plan_id=None, **answers):
    res = client.post(PLAN + "/start", json={**START, **answers, **({"plan_id": plan_id} if plan_id else {})})
    assert res.status_code == 201, res.text
    return res.json()


def change(client, plan_id, **extra):
    return client.post(PLAN + "/change", json={"plan_id": plan_id, **extra})


def add_income(client, amount, day="2026-09-01"):
    assert client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": amount, "frequency": "monthly",
                                            "date": day}).status_code == 201


def add_expense(client, amount, category, day, **extra):
    res = client.post("/api/expenses", json={"amount": amount, "category": category, "date": day, **extra})
    assert res.status_code == 201, res.text
    return res.json()


# ===== STARTING PLAN =====
@pytest.mark.parametrize("life, rent, loan, irregular, expected", [
    ("working", True, True, True, "debt_focus"),           # loan first
    ("studying", True, True, False, "debt_focus"),
    ("working", True, False, True, "sixty_solution"),      # then rent
    ("studying", True, False, False, "sixty_solution"),
    ("working", False, False, True, "zero_based"),         # then irregular income
    ("studying", False, False, True, "zero_based"),
    ("studying", False, False, False, "student_caps"),     # then studying
    ("both", False, False, False, "student_caps"),
    ("working", False, False, False, "fifty_thirty_twenty"),
])
def test_starting_plan_mapping(life, rent, loan, irregular, expected):
    assert suggest_start_plan(life, rent, loan, irregular)[0] == expected


def test_plans_add_up_to_100():
    for plan in PLANS.values():
        assert plan["needs"] + plan["wants"] + plan["savings"] == 100


def test_pay_yourself_first_saves_at_least_as_much_as_any_plan():
    assert PLANS["pay_yourself_first"]["savings"] == max(plan["savings"] for plan in PLANS.values())


def test_start_once_any_plan_then_locked(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    assert logged_in.get(PLAN).json()["has_plan"] is False
    preview = logged_in.post(PLAN + "/start/preview", json={**START, "life": "studying"}).json()
    assert preview == {"plan_id": "student_caps", "reason": "START_STUDENT"}
    state = start(logged_in, "zero_based", life="studying")  # a different starting plan is allowed here
    assert state["current"] == {"plan_id": "zero_based", "start_month": "2026-11", "reason": "start"}
    res = logged_in.post(PLAN + "/start", json=START)
    assert res.status_code == 409 and res.json()["code"] == "PLAN_ALREADY_SET"


# ===== WEEKLY → MONTHLY =====
def test_weekly_expense_counts_52_over_12(logged_in):
    expense = add_expense(logged_in, 120, "Transport", "2026-11-02", frequency="weekly")
    assert expense["frequency"] == "weekly" and expense["entered_amount"] == 120 and expense["amount"] == 520
    assert expense["is_fixed"] == 1
    summary = logged_in.get("/api/summary", params={"month": "2026-12"}).json()
    assert summary["spent"] == 520  # repeats every month from its start
    one_off = add_expense(logged_in, 50, "Groceries", "2026-11-03", frequency="one-off")
    assert one_off["frequency"] == "one-off" and one_off["is_fixed"] == 0


def test_old_clients_without_frequency_still_work(logged_in):
    assert add_expense(logged_in, 900, "Bills", "2026-11-01", is_fixed=True)["frequency"] == "monthly"


# ===== ENOUGH DATA (14+ days or 10+ expenses) =====
def test_enough_data_rule():
    assert not has_enough_data([], "2026-11-20")
    assert not has_enough_data([{"date": "2026-11-07"}], "2026-11-20")  # 13 days
    assert has_enough_data([{"date": "2026-11-06"}], "2026-11-20")      # 14 days
    assert not has_enough_data([{"date": "2026-11-19"}] * 9, "2026-11-20")
    assert has_enough_data([{"date": "2026-11-19"}] * 10, "2026-11-20")  # 10 expenses, same day


def test_api_waits_for_data(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    start(logged_in)
    assert logged_in.get(PLAN).json()["recommendation"] == {"action": "wait"}


# ===== SUGGESTION RULES (from real spending) =====
def test_no_income_suggests_zero_based():
    advice = build_recommendation(month("2026-10", income=None), "fifty_thirty_twenty")
    assert (advice["action"], advice["plan_id"], advice["rule"]) == ("switch", "zero_based", "NO_INCOME")


@pytest.mark.parametrize("needs, expected, rule", [(6000, "pay_yourself_first", "NEEDS_OK"),
                                                   (6001, "zero_based", "NEEDS_HIGH"),
                                                   (6800, "zero_based", "NEEDS_HIGH")])
def test_essentials_rule(needs, expected, rule):
    advice = build_recommendation(month("2026-10", needs=needs, wants=1000), "student_caps")
    assert advice["plan_id"] == expected and advice["rule"] == rule
    assert advice["numbers"]["percent"] == round(needs / 100) and advice["numbers"]["months"] == ["2026-10"]


def test_already_on_the_suggested_style_keeps_it():
    advice = build_recommendation(month("2026-10"), "pay_yourself_first")
    assert advice["action"] == "keep" and advice["plan_id"] == "pay_yourself_first"


def test_looser_style_is_not_unlocked_by_wants_overspending():
    assert is_looser("pay_yourself_first", "sixty_solution")  # wants 30 > 10
    over = build_recommendation(month("2026-10", needs=4000, wants=3000), "sixty_solution")  # wants 30% > 10%
    assert over["action"] == "keep" and over["rule"] == "WANTS_OVER"
    within = build_recommendation(month("2026-10", needs=4000, wants=500), "sixty_solution")  # wants 5%
    assert within["action"] == "switch" and within["plan_id"] == "pay_yourself_first" and within["looser"]


@pytest.mark.parametrize("current", list(PLANS))
def test_wants_overspending_never_gives_a_looser_style(current):
    advice = build_recommendation(month("2026-10", needs=3000, wants=6000), current)
    assert not (advice["action"] == "switch" and advice["looser"])


# ===== JUDGING A MONTH + STREAKS + COST =====
def test_judge_month_on_plan_and_over():
    assert judge_month(month("2026-10"), "fifty_thirty_twenty")["status"] == "on_plan"
    over = judge_month(month("2026-10", wants=3600), "fifty_thirty_twenty")
    assert over["status"] == "over" and over["wants_over"] == 600
    assert judge_month(month("2026-10", income=None), "fifty_thirty_twenty")["status"] == "no_data"


def test_debt_first_counts_loans_as_the_20_percent():
    figures = month("2026-10", needs=4500, loans=1500, saved=500)
    assert judge_month(figures, "debt_focus")["status"] == "on_plan"
    assert judge_month(figures, "fifty_thirty_twenty")["status"] == "over"  # loans are needs there


def test_streak_counting_and_reset():
    rows = lambda *statuses: [{"month": f"2026-{i + 1:02d}", "status": s} for i, s in enumerate(statuses)]  # noqa: E731
    assert count_streak(rows("on_plan", "on_plan", "on_plan")) == 3
    assert count_streak(rows("on_plan", "over", "on_plan")) == 1
    assert count_streak(rows("on_plan", "on_plan", "over")) == 0
    assert count_streak([{"month": "2026-01", "status": "on_plan"}, {"month": "2026-03", "status": "on_plan"}]) == 1
    assert count_streak([]) == 0


def test_switch_cost():
    goal = {"name": "Bike", "target_amount": 12000, "saved_amount": 0}
    cost = switch_cost("fifty_thirty_twenty", "student_caps", 20000, goal)
    assert cost == {"save_less": 2000, "goal": {"name": "Bike", "months_later": 3}}  # 3 months at 20% → 6 at 10%
    assert switch_cost("fifty_thirty_twenty", "student_caps", 0, goal)["goal"] is None  # no income: no goal line


# ===== COMMITMENT RULES (through the API, so the screen can't be bypassed) =====
def test_mid_month_change_starts_next_month(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    start(logged_in)
    state = change(logged_in, "sixty_solution").json()  # stricter: fewer wants
    assert state["current"]["plan_id"] == "fifty_thirty_twenty"  # this month is still judged on the old plan
    assert state["pending"] == {"plan_id": "sixty_solution", "start_month": "2026-12"}
    aim = lambda m: logged_in.get("/api/summary", params={"month": m}).json()["plan_aim"]  # noqa: E731
    assert aim("2026-11") == {"needs": 50, "wants": 30, "savings": 20}
    assert aim("2026-12") == {"needs": 70, "wants": 10, "savings": 20}
    at(monkeypatch, "2026-12-01")
    state = logged_in.get(PLAN).json()
    assert state["current"]["plan_id"] == "sixty_solution" and state["pending"] is None


def test_one_change_a_month_and_cancel(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    start(logged_in)
    assert change(logged_in, "sixty_solution").status_code == 200
    res = change(logged_in, "zero_based")
    assert res.status_code == 409 and res.json()["code"] == "PLAN_CHANGE_LIMIT"
    assert logged_in.delete(PLAN + "/pending").json()["pending"] is None
    assert change(logged_in, "zero_based").status_code == 200  # cancelled → a new choice is allowed
    at(monkeypatch, "2026-12-03")
    assert change(logged_in, "sixty_solution").status_code == 200  # a new month: one more change


def test_looser_switch_needs_confirm_and_reason(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    add_income(logged_in, 20000)
    start(logged_in)
    assert logged_in.post("/api/goals", json={"name": "Bike", "target_amount": 12000, "deadline": "2028-01-01",
                                              "priority": 1}).status_code == 201
    preview = logged_in.get(PLAN + "/preview", params={"plan_id": "student_caps"}).json()
    assert preview["looser"] and preview["save_less"] == 2000 and preview["goal"]["months_later"] == 3
    res = change(logged_in, "student_caps")
    assert res.status_code == 409 and res.json()["code"] == "CONFIRM_LOOSER"
    assert res.json()["params"]["save_less"] == 2000
    res = change(logged_in, "student_caps", confirm_looser=True)
    assert res.status_code == 400 and res.json()["code"] == "REASON_REQUIRED"
    res = change(logged_in, "student_caps", confirm_looser=True, reason="rent_up", start_now=True)
    assert res.status_code == 400 and res.json()["code"] == "LOOSER_STARTS_NEXT_MONTH"
    state = change(logged_in, "student_caps", confirm_looser=True, reason="rent_up").json()
    assert state["pending"]["start_month"] == "2026-12"
    assert state["history"][0]["reason"] == "rent_up" and not state["history"][0]["was_recommended"]


def test_stricter_switch_needs_no_confirm_and_may_start_now(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    start(logged_in, "student_caps")
    state = change(logged_in, "fifty_thirty_twenty", start_now=True).json()  # saves more: stricter
    assert state["current"]["plan_id"] == "fifty_thirty_twenty" and state["pending"] is None
    assert logged_in.get("/api/summary", params={"month": "2026-11"}).json()["plan_aim"]["savings"] == 20


def test_same_plan_and_no_plan_are_refused(logged_in, monkeypatch):
    at(monkeypatch, "2026-11-15")
    assert change(logged_in, "zero_based").json()["code"] == "NO_PLAN_YET"
    start(logged_in)
    assert change(logged_in, "fifty_thirty_twenty").json()["code"] == "SAME_PLAN"
    assert logged_in.post(PLAN + "/change", json={"plan_id": "made_up"}).status_code == 422


def test_switching_keeps_past_plans_and_late_expenses_count(logged_in, monkeypatch):
    at(monkeypatch, "2026-10-01")
    add_income(logged_in, 10000)
    start(logged_in)
    add_expense(logged_in, 4000, "Shopping", "2026-10-05")  # wants 40% > 30%: October is over the plan
    at(monkeypatch, "2026-11-10")
    state = logged_in.get(PLAN).json()
    october = state["last_result"]
    assert october["month"] == "2026-10" and october["status"] == "over" and october["wants_over"] == 1000
    assert october["tips"] and all(t["code"] != "LOOSER_PLAN" for t in october["tips"])
    advice = state["recommendation"]
    assert not (advice["action"] == "switch" and advice["looser"])  # never a looser plan for wants
    change(logged_in, "student_caps", confirm_looser=True, reason="other")
    add_expense(logged_in, 500, "Shopping", "2026-10-07")  # logged late: worked out when viewed, so it counts
    at(monkeypatch, "2026-12-02")
    results = logged_in.get(PLAN).json()["results"]
    past = next(r for r in results if r["month"] == "2026-10")
    assert past["plan_id"] == "fifty_thirty_twenty"  # still judged on October's plan after the switch
    assert past["status"] == "over" and past["wants_over"] == 1500


def test_recommended_switch_skips_friction(logged_in, monkeypatch):
    at(monkeypatch, "2026-10-01")
    add_income(logged_in, 10000)
    start(logged_in, "zero_based")
    add_expense(logged_in, 4000, "Groceries", "2026-10-02")  # essentials 40% → pay yourself first
    at(monkeypatch, "2026-10-20")
    state = logged_in.get(PLAN).json()
    advice = state["recommendation"]
    assert advice["action"] == "switch" and advice["plan_id"] == "pay_yourself_first" and advice["looser"]
    assert advice["numbers"]["percent"] == 40 and advice["numbers"]["months"] == ["2026-10"]
    assert state["style_changed_at"]
    state = change(logged_in, "pay_yourself_first", from_recommendation=True).json()  # no confirm / reason needed
    assert state["history"][0]["was_recommended"] and state["history"][0]["reason"] == "recommended"
    assert state["pending"]["start_month"] == "2026-11"


def test_streak_through_the_api(logged_in, monkeypatch):
    at(monkeypatch, "2026-09-01")
    add_income(logged_in, 10000)
    start(logged_in)
    for day in ("2026-09-03", "2026-10-03"):
        add_expense(logged_in, 3000, "Groceries", day)
        assert logged_in.post("/api/savings/entries", json={"kind": "deposit", "amount": 2000, "date": day,
                                                            "place": "general"}).status_code == 201  # 20% saved
    at(monkeypatch, "2026-11-05")
    assert logged_in.get(PLAN).json()["streak"] == 2
    add_expense(logged_in, 4000, "Shopping", "2026-11-06")  # November over (wants 40%)
    at(monkeypatch, "2026-12-01")
    assert logged_in.get(PLAN).json()["streak"] == 0  # reset


def test_one_user_never_sees_another_users_plan(new_client, sent_codes, monkeypatch):
    at(monkeypatch, "2026-11-15")
    asha = log_in(new_client(), sent_codes)
    bob = log_in(new_client(), sent_codes, "bob@example.com")
    start(asha, "zero_based")
    change(asha, "sixty_solution")
    bob_state = bob.get(PLAN).json()
    assert bob_state["has_plan"] is False and "history" not in bob_state
    assert bob.delete(PLAN + "/pending").json()["code"] == "NO_PENDING_CHANGE"  # can't touch Asha's change
    assert asha.get(PLAN).json()["pending"]["plan_id"] == "sixty_solution"


def test_demo_date_is_ignored_in_production(monkeypatch):
    import datetime
    import routes.plan
    monkeypatch.setenv("DEMO_TODAY", "2030-01-01")
    monkeypatch.setenv("APP_ENV", "production")
    assert routes.plan.plan_today() == datetime.date.today().isoformat()
