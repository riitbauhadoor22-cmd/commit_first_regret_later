# test_dashboard.py — the Dashboard tab: every number comes from the user's records, nothing is made up, and the AI
# is never used. Covers the 15 cases of the brief (new user, income + expenses, savings + goals, no goals, one /
# several / incomplete loans, 6+ months / 1 month of history, weekly budget kept / exceeded, expenses without a date,
# edits and deletes, several goals, other users) plus the health score rules. All data is fictional.
from datetime import date, timedelta

import pytest

import database
import routes.dashboard
from conftest import log_in
from models import WeeklyBudget
from services.dashboard import (build_dashboard, build_health_score, build_loans, build_spending_series,
                                find_new_badges, get_finished_weeks, get_week_start, project_loan)

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]
NO_SAVINGS = {"bank_balance": None, "monthly_target": None, "safety_net_saved": 0}


# ===== HELPERS =====
def dashboard(client):
    res = client.get("/api/dashboard", params={"today": TODAY.isoformat()})
    assert res.status_code == 200
    return res.json()


def add_income(client, amount=20000, day=None):
    res = client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": amount, "frequency": "monthly",
                                           "date": (day or TODAY.replace(day=1)).isoformat()})
    assert res.status_code == 201
    return res.json()["id"]


def add_expense(client, amount, category="Groceries", day=None):
    body = {"amount": amount, "category": category}
    if day is not None:
        body["date"] = day.isoformat()
    res = client.post("/api/expenses", json=body)
    assert res.status_code == 201
    return res.json()["id"]


def add_goal(client, name="Bike", target=10000, saved=0):
    assert client.post("/api/goals", json={"name": name, "target_amount": target, "deadline": "2028-01-01",
                                           "priority": 2}).status_code == 201
    goal = [g for g in client.get("/api/goals").json()["goals"] if g["name"] == name][0]
    if saved:
        assert client.post(f"/api/goals/{goal['id']}/add-money", json={"amount": saved}).status_code == 200
    return goal["id"]


def add_loan(client, balance=24000, rate=12, payment=1000, name="Phone loan"):
    res = client.post("/api/my-loans", json={"name": name, "balance": balance, "annual_rate": rate,
                                             "monthly_payment": payment})
    assert res.status_code == 201


def records(**parts):
    base = {"incomes": [], "expenses": [], "deposits": [], "goals": [], "loans": [], "savings_row": None}
    base.update(parts)
    return base


def expense(amount, day, category="Groceries", kind="need", fixed=0):
    return {"amount": amount, "category": category, "kind": kind, "date": day, "is_fixed": fixed,
            "created_at": day + "T10:00:00", "note": ""}


# ===== 1. NEW USER =====
def test_new_user_sees_an_empty_dashboard_not_fake_numbers(logged_in, fake_groq):
    data = dashboard(logged_in)
    assert data["is_new_user"] is True
    assert data["balance"]["available"] is False and set(data["balance"]["missing"]) == {"income", "expenses"}
    assert data["spending"] == {"available": False, "months": []}
    assert data["savings"]["available"] is False and data["loans"]["available"] is False
    assert data["health"]["available"] is False and data["health"]["reason"] == "NOT_ENOUGH_DATA"
    assert data["weekly"]["available"] is False and data["jar"]["available"] is False
    assert data["badges"]["earned"] == [] and data["recap"]["statements"] == []
    assert fake_groq["calls"] == 0  # the dashboard never uses the AI


# ===== 2. INCOME + EXPENSES =====
def test_income_and_expenses(logged_in):
    add_income(logged_in, 20000)
    add_expense(logged_in, 3000, "Groceries")
    add_expense(logged_in, 1200, "Shopping")
    data = dashboard(logged_in)
    balance = data["balance"]
    assert balance["available"] and balance["balance"] == 15800 and balance["state"] == "positive"
    assert balance["excludes_loans"] is True  # loans not given: not taken off, and said so
    assert data["spending"]["months"] == [{"month": MONTH, "total": 4200,
                                           "by_category": {"Groceries": 3000, "Shopping": 1200}, "change_percent": None}]
    recap = data["recap"]
    assert (recap["income"], recap["expenses"], recap["remaining"]) == (20000, 4200, 15800)
    assert recap["biggest_category"] == {"category": "Groceries", "amount": 3000}
    codes = [s["code"] for s in recap["statements"]]
    assert "TOP_CATEGORY" in codes and "MONTH_SO_FAR" in codes and "LEFT_POSITIVE" in codes
    assert data["is_new_user"] is False


# ===== 3. SAVINGS + GOALS (no double counting) =====
def test_savings_contributions_and_goals(logged_in):
    add_income(logged_in, 20000)
    add_expense(logged_in, 5000)
    add_goal(logged_in, "Laptop", 20000, saved=8000)
    data = dashboard(logged_in)
    assert data["balance"]["balance"] == 7000  # 20,000 − 5,000 − 8,000 saved (deposits are not expenses)
    assert data["balance"]["put_aside"] == 8000 and data["balance"]["bank_balance"] is None
    point = data["savings"]["months"][-1]
    assert point == {"month": MONTH, "saved": 8000, "income": 20000, "rate": 40.0} and data["savings"]["guide"] == 20
    jar = data["jar"]["goals"][0]
    assert (jar["name"], jar["saved"], jar["target"], jar["remaining"], jar["percent"]) == ("Laptop", 8000, 20000,
                                                                                          12000, 40.0)


# ===== 4. NO SAVINGS GOALS =====
def test_no_savings_goals(logged_in):
    add_income(logged_in)
    data = dashboard(logged_in)
    assert data["jar"] == {"available": False, "goals": [], "overall_percent": None}
    assert data["savings"]["available"] is False and data["savings"]["reason"] == "NO_SAVINGS"


# ===== 5 + 6 + 7. LOANS =====
def test_one_loan(logged_in):
    add_income(logged_in, 20000)
    add_expense(logged_in, 4000)
    add_loan(logged_in, 24000, 12, 1000)
    data = dashboard(logged_in)
    loan = data["loans"]["loans"][0]
    assert loan["available"] and loan["history"] is None  # history isn't stored: projection only
    assert loan["points"][0] == {"month": MONTH, "balance": 24000}
    assert loan["points"][-1]["balance"] == 0 and loan["payoff_month"] == loan["points"][-1]["month"]
    assert 27 <= loan["months_left"] <= 29  # 24,000 at 12% a year paid 1,000 a month: about 28 months
    assert data["balance"]["balance"] == 15000 and data["balance"]["excludes_loans"] is False
    assert data["recap"]["loan_repayments"] == 1000


def test_several_loans(logged_in):
    add_loan(logged_in, 10000, 0, 1000, "A")
    add_loan(logged_in, 3000, 0, 1000, "B")
    loans = dashboard(logged_in)["loans"]
    assert loans["outstanding"] == 13000 and loans["monthly_payments"] == 2000
    assert [p["balance"] for p in loans["total"][:5]] == [13000, 11000, 9000, 7000, 6000]  # B is paid off after 3 months
    assert [item["months_left"] for item in loans["loans"]] == [10, 3]


def test_incomplete_or_unpayable_loans_are_not_projected():
    assert project_loan(10000, None, 500, "2026-11")["reason"] == "MISSING_DETAILS"
    assert project_loan(10000, 12, None, "2026-11")["reason"] == "MISSING_DETAILS"
    too_low = project_loan(100000, 24, 1000, "2026-11")  # interest is 2,000 a month: never paid off
    assert too_low["available"] is False and too_low["reason"] == "PAYMENT_TOO_LOW" and too_low["points"] == []
    loans = [{"id": "1", "name": "", "balance": 5000, "annual_rate": 0, "monthly_payment": 500},
             {"id": "2", "name": "", "balance": 100000, "annual_rate": 24, "monthly_payment": 1000}]
    result = build_loans(loans, "provided", "2026-11")
    assert result["total"] is None  # no combined line when one loan can't be projected
    assert build_loans([], "missing", "2026-11") == {"available": False, "state": "missing", "loans": [], "total": None}


# ===== 8 + 9. HISTORY =====
def test_six_or_more_months_show_only_the_last_six_with_data():
    days = ["2026-01-10", "2026-03-10", "2026-04-10", "2026-05-10", "2026-07-10", "2026-08-10", "2026-09-10",
            "2026-10-10", "2026-11-10"]
    series = build_spending_series([expense(100 * (i + 1), d) for i, d in enumerate(days)], "2026-11")
    months = [point["month"] for point in series["months"]]
    assert months == ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]  # 2026-06 had nothing: not a fake 0
    assert series["months"][0]["change_percent"] is None  # June has no data
    assert series["months"][1]["change_percent"] == round((600 - 500) / 500 * 100, 1)


def test_only_one_month_of_history():
    series = build_spending_series([expense(250, "2026-11-03")], "2026-11")
    assert len(series["months"]) == 1 and series["months"][0]["change_percent"] is None


def test_recap_compares_with_last_month(logged_in):
    last_month = TODAY.replace(day=1) - timedelta(days=1)
    add_income(logged_in, 20000, last_month.replace(day=1))
    add_expense(logged_in, 5000, "Groceries", last_month)
    add_expense(logged_in, 4000, "Groceries", TODAY)
    recap = dashboard(logged_in)["recap"]
    codes = {s["code"]: s["params"] for s in recap["statements"]}
    assert codes["SPENDING_DOWN"] == {"percent": 20} and "TOP_CATEGORY_SAME" in codes
    assert recap["expenses_change_percent"] == -20 and "MONTH_SO_FAR" not in codes


# ===== 10 + 11 + 12. WEEKLY BUDGET + BADGES =====
MONDAY = date(2026, 11, 2)


def week_expenses(amounts):
    return [expense(amount, (MONDAY + timedelta(days=i)).isoformat(), "Food & drinks", "want")
            for i, amount in enumerate(amounts) if amount]


def test_week_within_budget_earns_first_week():
    budget = {"amount": 1000, "set_on": MONDAY.isoformat()}
    weeks = get_finished_weeks(week_expenses([200, 150, 0, 300, 0, 100, 0]), budget, date(2026, 11, 10))
    assert len(weeks) == 1 and weeks[0]["kept"] and weeks[0]["spent"] == 750 and weeks[0]["days_recorded"] == 4
    assert find_new_badges(weeks, [], set()) == {"FIRST_WEEK": "2026-11-08"}
    assert find_new_badges(weeks, [], {"FIRST_WEEK"}) == {}  # never twice


def test_week_over_budget_earns_nothing():
    budget = {"amount": 500, "set_on": MONDAY.isoformat()}
    weeks = get_finished_weeks(week_expenses([200, 150, 0, 300]), budget, date(2026, 11, 10))
    assert weeks[0]["kept"] is False and find_new_badges(weeks, [], set()) == {}


def test_a_week_with_too_little_recorded_is_not_proof():
    budget = {"amount": 5000, "set_on": MONDAY.isoformat()}
    weeks = get_finished_weeks(week_expenses([200, 0, 0, 0, 0, 0, 0]), budget, date(2026, 11, 10))
    assert weeks[0]["tracked"] is False and weeks[0]["kept"] is False  # 1 day recorded: not counted
    assert get_finished_weeks([], budget, date(2026, 11, 10))[0]["kept"] is False  # nothing recorded at all


def test_unfinished_week_and_weeks_before_the_budget_are_not_counted():
    budget = {"amount": 1000, "set_on": "2026-11-04"}  # a Wednesday → counting starts Monday 9 Nov
    assert get_finished_weeks(week_expenses([100, 100, 100]), budget, date(2026, 11, 12)) == []
    assert get_week_start(date(2026, 11, 15)) == date(2026, 11, 9)  # Sunday belongs to the week of Monday 9th


def test_more_badges():
    def week(start, kept):
        return {"week_start": start, "week_end": start, "kept": kept, "tracked": True}
    weeks = [week("w1", True), week("w2", False), week("w3", True), week("w4", True), week("w5", True)]
    found = find_new_badges(weeks, [{"week_end": f"s{i}", "saved": True} for i in range(4)], set())
    assert found == {"FIRST_WEEK": "w1", "BUDGET_KEEPER": "w4", "CONSISTENT_PLANNER": "w5", "SAVINGS_STREAK": "s3"}


def test_expense_without_a_date_counts_today(logged_in):
    add_expense(logged_in, 300, "Transport")  # no date → today (ExpenseForm)
    data = dashboard(logged_in)
    assert data["spending"]["months"][-1]["total"] == 300
    assert logged_in.put("/api/dashboard/weekly-budget", json={"amount": 2000, "today": TODAY.isoformat()}).status_code == 200
    weekly = dashboard(logged_in)["weekly"]
    assert weekly["available"] and weekly["spent"] == 300 and weekly["left"] == 1700 and weekly["state"] == "on_track"


def test_weekly_budget_route_and_badges_are_kept(logged_in, monkeypatch):
    last_monday = get_week_start(TODAY) - timedelta(days=7)
    expense_ids = [add_expense(logged_in, 100, "Food & drinks", last_monday + timedelta(days=i)) for i in range(3)]
    assert logged_in.put("/api/dashboard/weekly-budget", json={"amount": 1000, "today": TODAY.isoformat()}).status_code == 200
    with database.open_db() as db:  # pretend the budget was set before last week
        db.query(WeeklyBudget).one().set_on = last_monday
    data = dashboard(logged_in)
    assert [b["code"] for b in data["badges"]["earned"]] == ["FIRST_WEEK"] and data["badges"]["new"] == ["FIRST_WEEK"]
    assert data["badges"]["earned"][0]["earned_on"] == (last_monday + timedelta(days=6)).isoformat()
    # ===== 13. editing / deleting old expenses never takes a badge away (and never gives it twice)
    for expense_id in expense_ids:
        assert logged_in.delete(f"/api/expenses/{expense_id}").status_code == 200
    again = dashboard(logged_in)
    assert [b["code"] for b in again["badges"]["earned"]] == ["FIRST_WEEK"] and again["badges"]["new"] == []
    assert logged_in.put("/api/dashboard/weekly-budget", json={"amount": None}).status_code == 200
    assert dashboard(logged_in)["weekly"]["available"] is False
    assert len(dashboard(logged_in)["badges"]["earned"]) == 1
    assert logged_in.put("/api/dashboard/weekly-budget", json={"amount": -5}).status_code == 422


def test_edits_and_deletes_update_the_numbers(logged_in):
    add_income(logged_in, 10000)
    expense_id = add_expense(logged_in, 2000)
    assert dashboard(logged_in)["balance"]["balance"] == 8000
    logged_in.put(f"/api/expenses/{expense_id}", json={"amount": 3500, "category": "Bills", "date": TODAY.isoformat()})
    data = dashboard(logged_in)
    assert data["balance"]["balance"] == 6500 and data["spending"]["months"][-1]["by_category"] == {"Bills": 3500}
    logged_in.delete(f"/api/expenses/{expense_id}")
    data = dashboard(logged_in)
    assert data["spending"]["available"] is False and data["balance"]["available"] is False  # expenses gone = unknown


# ===== 14. SEVERAL GOALS =====
def test_several_goals_each_have_their_own_jar(logged_in):
    add_goal(logged_in, "Emergency Fund", 20000, saved=8000)
    add_goal(logged_in, "Phone", 5000, saved=5000)
    add_goal(logged_in, "Trip", 30000)
    jar = dashboard(logged_in)["jar"]
    jars = {goal["name"]: goal for goal in jar["goals"]}
    assert jar["overall_percent"] == 23.6  # (8,000 + 5,000) / 55,000 — the Dashboard tile "Savings · 24%"
    assert jars["Emergency Fund"]["percent"] == 40 and jars["Emergency Fund"]["remaining"] == 12000
    assert jars["Phone"]["percent"] == 100 and jars["Phone"]["status"] == "Done"
    assert jars["Trip"]["percent"] == 0 and jars["Trip"]["saved"] == 0


# ===== 15. OTHER USERS =====
def test_other_users_never_see_my_dashboard(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    add_income(asha)
    add_expense(asha, 999)
    add_goal(asha, "Asha goal", 1000, saved=500)
    add_loan(asha)
    ravi = log_in(new_client(), sent_codes, "ravi@example.com")
    data = dashboard(ravi)
    assert data["is_new_user"] is True and data["jar"]["goals"] == [] and data["loans"]["loans"] == []
    assert "Asha goal" not in str(data) and "999" not in str(data["spending"])


# ===== HEALTH SCORE =====
def test_health_score_with_complete_data(logged_in):
    add_income(logged_in, 20000)
    add_expense(logged_in, 6000, "Groceries")
    add_expense(logged_in, 2000, "Shopping")
    add_goal(logged_in, "Bike", 10000, saved=2000)
    logged_in.put("/api/info-choices", json={"topic": "loans", "none": True})
    health = dashboard(logged_in)["health"]
    assert health["available"] and 0 <= health["score"] <= 100
    assert health["level"] in ("needs_attention", "fair", "good", "excellent") and health["measured_weight"] == 100
    parts = {part["part"]: part for part in health["parts"]}
    assert parts["commitments"]["points"] == 20  # "I don't have a loan": nothing to worry about
    assert parts["budget"]["points"] == 30  # within income and a positive balance
    assert health["strength"] and "improve" in health


def test_missing_data_is_skipped_not_punished():
    income = [{"amount": 20000, "frequency": "monthly", "date": "2026-11-01"}]
    expenses = [expense(5000, "2026-11-05")]
    data = records(incomes=income, expenses=expenses)
    rows = [{"category": "Groceries", "budget": None, "over_by": 0}]
    health = build_health_score(data, set(), "2026-11", rows, [])
    parts = {part["part"]: part for part in health["parts"]}
    assert parts["savings"]["points"] is None and parts["savings"]["skipped_reason"] == "NEED_SAVINGS"
    assert parts["commitments"]["points"] is None and parts["commitments"]["skipped_reason"] == "NEED_LOANS"
    assert health["available"] and health["measured_weight"] == 55 and health["score"] == 100


def test_not_enough_data_gives_no_score():
    health = build_health_score(records(expenses=[expense(5000, "2026-11-05")]), set(), "2026-11", [], [])
    assert health["available"] is False and health["reason"] == "NOT_ENOUGH_DATA"


def test_dashboard_is_the_same_every_time():  # deterministic: same records → same answer
    data = records(incomes=[{"amount": 9000, "frequency": "monthly", "date": "2026-10-01"}],
                   expenses=[expense(4000, "2026-10-05"), expense(3000, "2026-11-05", "Shopping", "want")])
    first = build_dashboard(data, set(), NO_SAVINGS, [], None, set(), date(2026, 11, 14))
    second = build_dashboard(data, set(), NO_SAVINGS, [], None, set(), date(2026, 11, 14))
    assert first == second and first["health"]["available"]


@pytest.mark.parametrize("today", ["abc", "2026-13-01"])
def test_bad_today_is_rejected(logged_in, today):
    assert logged_in.get("/api/dashboard", params={"today": today}).status_code == 422


def test_far_away_today_falls_back_to_the_server_date(logged_in):
    assert logged_in.get("/api/dashboard", params={"today": "1990-01-01"}).json()["today"] == TODAY.isoformat()
    assert routes.dashboard.pick_today(None) == TODAY
