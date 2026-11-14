# test_weekly_suggestion.py — the suggested weekly budget (GET /api/dashboard → "weekly_suggestion"): from category
# budgets, from income − fixed bills − loans − saving, never negative (too_low flag), the user's saved weekly budget
# is never overwritten, no double counting of a loan also recorded as a fixed bill, and other users' data is never used.
# All data is fictional.
import calendar
from datetime import date

from conftest import log_in
from services.dashboard import build_weekly_suggestion, round_to_ten

TODAY = date.today()
WEEKS = calendar.monthrange(TODAY.year, TODAY.month)[1] / 7  # weeks in this month = days ÷ 7
FIRST = TODAY.replace(day=1).isoformat()


# ===== HELPERS =====
def suggestion(client):
    res = client.get("/api/dashboard", params={"today": TODAY.isoformat()})
    assert res.status_code == 200
    return res.json()


def add_income(client, amount):
    assert client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": amount,
                                            "frequency": "monthly", "date": FIRST}).status_code == 201


def add_fixed_bill(client, amount, category="Bills"):
    assert client.post("/api/expenses", json={"amount": amount, "category": category, "date": FIRST,
                                              "is_fixed": True}).status_code == 201


def set_target(client, amount):
    assert client.put("/api/savings", json={"bank_balance": None, "monthly_target": amount}).status_code == 200


# ===== TESTS =====
def test_suggestion_from_category_budgets(logged_in):
    add_income(logged_in, 50000)  # ignored: budgets win
    for category, limit in (("Groceries", 3000), ("Transport", 1000)):
        assert logged_in.put("/api/budgets", json={"category": category, "monthly_limit": limit}).status_code == 200
    s = suggestion(logged_in)["weekly_suggestion"]
    assert s["available"] is True and s["source"] == "budgets" and s["code"] == "budgets"
    assert s["amount"] == round_to_ten(4000 / WEEKS) and s["amount"] % 10 == 0
    assert s["params"] == {"monthly": 4000, "categories": 2}


def test_suggestion_from_income_bills_loans_and_saving(logged_in):
    add_income(logged_in, 20000)
    add_fixed_bill(logged_in, 5000)
    set_target(logged_in, 3000)
    assert logged_in.post("/api/my-loans", json={"name": "Phone", "balance": 24000, "annual_rate": 12,
                                                 "monthly_payment": 1000}).status_code == 201
    s = suggestion(logged_in)["weekly_suggestion"]
    assert s["source"] == "income" and s["too_low"] is False
    assert s["params"] == {"monthly": 11000, "income": 20000, "bills": 5000, "loans": 1000, "saving": 3000}
    assert s["amount"] == round_to_ten(11000 / WEEKS)


def test_default_saving_is_20_percent_and_loan_in_bills_is_not_counted_twice():
    records = {"incomes": [{"amount": 10000, "frequency": "monthly", "date": FIRST}],
               "expenses": [{"amount": 2000, "category": "Bills", "is_fixed": 1, "date": FIRST}],
               "loans": [{"monthly_payment": 2000, "start_date": FIRST, "created_at": FIRST}]}
    status = {"income": "provided", "loans": "provided"}
    s = build_weekly_suggestion(records, status, [], 2000, TODAY)  # 2000 = 20% of 10,000
    assert s["params"]["loans"] == 0 and s["params"]["monthly"] == 6000  # 10,000 − 2,000 bill (= the loan) − 2,000


def test_bills_and_savings_use_all_income_gives_the_flag(logged_in):
    add_income(logged_in, 5000)
    add_fixed_bill(logged_in, 4000)
    set_target(logged_in, 2000)
    s = suggestion(logged_in)["weekly_suggestion"]
    assert s["too_low"] is True and s["available"] is False and s["code"] == "tooLow"
    assert s["amount"] is None and s["params"]["monthly"] == 0  # never negative


def test_no_income_and_no_budgets_gives_no_suggestion(logged_in):
    s = suggestion(logged_in)["weekly_suggestion"]
    assert s == {"available": False, "too_low": False, "source": None, "code": "noData", "amount": None, "params": {},
                 "weeks": round(WEEKS, 2)}


def test_saved_weekly_budget_is_never_overwritten(logged_in):
    add_income(logged_in, 20000)
    assert logged_in.put("/api/dashboard/weekly-budget", json={"amount": 777, "today": TODAY.isoformat()}).status_code == 200
    data = suggestion(logged_in)
    assert data["weekly"]["budget"] == 777  # the user's own value stays
    assert data["weekly_suggestion"]["amount"] == round_to_ten(16000 / WEEKS)  # 20,000 − 20% saving; only offered


def test_other_users_data_is_never_used(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    add_income(asha, 30000)
    assert asha.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 4321}).status_code == 200
    ravi = log_in(new_client(), sent_codes, "ravi@example.com")
    assert suggestion(ravi)["weekly_suggestion"]["code"] == "noData"
    add_income(ravi, 10000)
    s = suggestion(ravi)["weekly_suggestion"]
    assert s["source"] == "income" and s["params"]["income"] == 10000 and "4321" not in str(s)
