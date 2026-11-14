# test_forecast.py — the spending forecast + goal "ready by" maths (services/forecast.py) and GET /api/forecast.
from datetime import date

from conftest import log_in
from services.forecast import build_goal_etas, build_spending_forecast, get_goal_eta

TODAY = date(2026, 11, 10)  # November has 30 days


def spend(amount, day="2026-11-02", fixed=False, category="Groceries"):
    return {"amount": amount, "date": day, "is_fixed": fixed, "category": category, "kind": "need", "note": ""}


def salary(amount):
    return {"amount": amount, "frequency": "monthly", "date": "2026-01-01"}


def forecast(expenses, incomes=(), budgets=(), saved=0, today=TODAY, month=None, loans=0):
    """saved = saved_this_month and loans = loan repayments, as services/month_summary.py passes them."""
    return build_spending_forecast(list(incomes), expenses, list(budgets), saved, today, month, loans)


# ===== SPENDING FORECAST =====
def test_normal_forecast_matches_the_example():  # Rs 6,000 by the 10th of a 30-day month → Rs 18,000
    f = forecast([spend(6000)], [salary(25000)], budgets=[{"category": "Groceries", "monthly_limit": 16000}],
                 saved=2000)
    assert f["available"] and f["forecast_spent"] == 18000 and f["budget"] == 16000 and f["over_budget"]
    assert f["left_at_month_end"] == 25000 - 18000 - 2000
    assert f["last_day"] == "2026-11-30"


def test_fixed_bills_are_added_once_not_per_day():
    f = forecast([spend(6000), spend(3000, "2026-01-05", fixed=True)], [salary(30000)], saved=0)
    assert f["forecast_spent"] == 18000 + 3000
    assert f["fixed_bills"] == 3000


def test_left_at_month_end_takes_off_saved_this_month_and_loans_once():
    # Old rule took max(deposits this month, target); goal / safety-net deposits are NOT this month's saving now
    f = forecast([spend(1000)], [salary(20000)], saved=2000, loans=1500)
    assert f["forecast_spent"] == 3000 + 1500 and f["loan_repayments"] == 1500  # loans once, not per day
    assert f["planned_savings"] == 2000 and f["left_at_month_end"] == 20000 - 4500 - 2000


def test_not_enough_data_gives_nothing():
    assert forecast([spend(500, "2026-11-02")], today=date(2026, 11, 4)) == {"available": False, "reason": "TOO_EARLY"}
    assert forecast([]) == {"available": False, "reason": "NO_SPENDING"}
    assert forecast([spend(500, "2026-01-05", fixed=True)])["reason"] == "NO_SPENDING"  # only fixed bills
    assert forecast([spend(500)], month="2026-10")["reason"] == "OTHER_MONTH"  # past months aren't guessed


def test_no_income_still_forecasts_spending_but_not_what_is_left():
    f = forecast([spend(1000)])
    assert f["forecast_spent"] == 3000 and f["income"] is None and f["left_at_month_end"] is None
    assert f["budget"] is None and not f["over_budget"]


def test_future_dated_expenses_are_not_counted_as_spent_so_far():
    assert forecast([spend(1000), spend(9000, "2026-11-25")])["forecast_spent"] == 3000


# ===== GOAL ETA =====
GOAL = {"id": "g1", "name": "Phone", "target_amount": 12000, "saved_amount": 3000}


def deposit(amount, day, goal_id="g1"):
    return {"amount": amount, "date": day, "goal_id": goal_id}


def test_goal_eta_from_the_last_three_months():
    deposits = [deposit(1500, "2026-09-05"), deposit(1500, "2026-10-05"), deposit(1500, "2026-11-05"),
                deposit(9999, "2026-06-01"),  # older than 3 months: ignored
                deposit(500, "2026-11-01", goal_id="other")]  # another goal: ignored
    eta = get_goal_eta(GOAL, deposits, TODAY)
    assert eta == {"per_month": 1500, "months": 6, "eta_month": "2027-05"}  # 9,000 left ÷ 1,500


def test_goal_started_recently_is_not_divided_by_three():
    eta = get_goal_eta(GOAL, [deposit(3000, "2026-11-02")], TODAY)
    assert eta["per_month"] == 3000 and eta["months"] == 3 and eta["eta_month"] == "2027-02"


def test_goal_eta_rounds_up_and_crosses_the_year():
    eta = get_goal_eta(GOAL, [deposit(2000, "2026-11-02")], date(2026, 11, 30))
    assert eta["months"] == 5 and eta["eta_month"] == "2027-04"  # 4.5 → 5


def test_no_savings_history_or_done_goal_gives_no_eta():
    assert get_goal_eta(GOAL, [], TODAY) is None
    assert get_goal_eta(GOAL, [deposit(1000, "2026-07-01")], TODAY) is None  # only older than 3 months
    done = dict(GOAL, saved_amount=12000)
    assert get_goal_eta(done, [deposit(1000, "2026-11-01")], TODAY) is None
    assert build_goal_etas([GOAL, done], [deposit(1000, "2026-11-01")], TODAY).keys() == {"g1"}


# ===== ROUTE =====
def test_forecast_route_uses_only_my_data(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    ben = log_in(new_client(), sent_codes, "ben@example.com")
    today = date.today()
    asha.post("/api/expenses", json={"amount": 600, "category": "Groceries", "date": today.isoformat()})
    mine = asha.get(f"/api/forecast?today={today.isoformat()}").json()
    theirs = ben.get(f"/api/forecast?today={today.isoformat()}").json()
    if today.day >= 5:
        assert mine["spending"]["available"] and mine["spending"]["everyday_so_far"] == 600
    assert theirs["spending"]["available"] is False
    assert theirs["goals"] == {}


def test_dashboard_has_forecast_and_jar_eta(logged_in):
    data = logged_in.get("/api/dashboard").json()
    assert "forecast" in data and "available" in data["forecast"]
