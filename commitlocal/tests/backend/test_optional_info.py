# test_optional_info.py — "Permission Denied": the user may skip income, expenses, loans or savings, and the rest
# keeps working. Missing information is "missing" (None on screen), never Rs 0; "I have none" is a real 0.
# Covers the 12 cases of the brief: each topic alone, nothing at all, adding later, editing / deleting,
# the summary updating, the AI only getting what was given, old data kept by migration 0006, other features fine.
# All data is fictional. Groq is always faked (conftest.py: fake_groq).
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

import database
from conftest import log_in
from models import SavingsSettings
from money import get_this_month, get_today

MONTH = get_this_month()
TODAY = get_today()


# ===== HELPERS =====
def summary(client):
    return client.get(f"/api/summary?month={MONTH}").json()


def status(client):
    return client.get(f"/api/info-status?month={MONTH}").json()


def analysis(client):
    return client.get(f"/api/insights?month={MONTH}").json()["analysis"]


def add_income(client, amount=20000):
    res = client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": amount,
                                           "frequency": "monthly", "date": TODAY})
    assert res.status_code == 201
    return res.json()["id"]


def add_expense(client, amount=3000, category="Groceries"):
    res = client.post("/api/expenses", json={"amount": amount, "category": category, "date": TODAY})
    assert res.status_code == 201
    return res.json()["id"]


def add_loan(client, payment=1500):
    res = client.post("/api/my-loans", json={"name": "Student loan", "balance": 40000, "annual_rate": 8,
                                             "monthly_payment": payment})
    assert res.status_code == 201
    return res.json()["loans"][-1]["id"]


def add_goal_with_money(client):
    assert client.post("/api/goals", json={"name": "Bike", "target_amount": 10000, "deadline": "2027-06-01",
                                           "priority": 2}).status_code == 201
    goal_id = client.get("/api/goals").json()["goals"][0]["id"]
    assert client.post(f"/api/goals/{goal_id}/add-money", json={"amount": 1000}).status_code == 200
    return goal_id


def savings_rows():
    with database.open_db() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(SavingsSettings))


# ===== 6. NOTHING GIVEN AT ALL =====
def test_user_who_skips_everything_can_use_the_app(logged_in, fake_groq):
    assert status(logged_in) == {"income": "missing", "expenses": "missing", "loans": "missing", "savings": "missing"}
    s = summary(logged_in)
    assert (s["income"], s["spent"], s["saved"], s["left_to_spend"]) == (None, None, None, None)
    assert s["needs_percent"] is None and s["wants_percent"] is None and s["savings_percent"] is None
    savings = logged_in.get("/api/savings").json()
    assert savings["bank_balance"] is None and savings["monthly_target"] is None and savings["info"] == "missing"
    assert logged_in.get("/api/goals").json() == {"goals": [], "monthly_target": None, "total_needed": 0,
                                                  "warning": None}
    assert logged_in.get("/api/my-loans").json() == {"loans": [], "total_monthly_payment": 0}
    assert savings_rows() == 0  # just looking never creates a Rs 0 savings record
    data = analysis(logged_in)
    assert data["enough_for_ai"] is False and data["observations"] == []
    assert set(data["data_gaps"]) == {"NO_INCOME", "NO_EXPENSES", "NO_LOANS", "NO_SAVINGS"}
    res = logged_in.post("/api/insights/generate", json={})
    assert res.status_code == 400 and res.json()["code"] == "AI_NOT_ENOUGH_DATA" and fake_groq["calls"] == 0
    # Educational features don't need any personal money data
    assert logged_in.get("/api/game/levels").status_code == 200
    assert logged_in.post("/api/game/attempts", json={"level": 1, "events_on": False}).status_code in (200, 201)
    assert logged_in.get("/api/inflation/projection", params={"target": 5000, "current": 0,
                                                              "deadline": "2027-12-01"}).status_code == 200


# ===== 1. INCOME ONLY =====
def test_income_but_no_expenses_or_loans(logged_in):
    add_income(logged_in)
    assert status(logged_in)["income"] == "provided" and status(logged_in)["expenses"] == "missing"
    s = summary(logged_in)
    assert s["income"] == 20000 and s["spent"] is None and s["left_to_spend"] is None  # no spending = unknown
    assert s["needs_percent"] is None
    data = analysis(logged_in)
    assert data["take_home_income"] == 20000 and data["needs"] is None and data["remaining"] is None
    assert {"NO_EXPENSES", "NO_LOANS"} <= set(data["data_gaps"])
    assert logged_in.get("/api/savings").json()["monthly_target"] == 4000  # 20% of income still works
    add_goal_with_money(logged_in)  # goals and loans can still be added
    add_loan(logged_in)


# ===== 2. EXPENSES ONLY =====
def test_expenses_but_no_income_or_loans(logged_in):
    add_expense(logged_in, 2500)
    s = summary(logged_in)
    assert s["spent"] == 2500 and s["income"] is None and s["left_to_spend"] is None
    assert s["needs_percent"] is None and s["categories"][1]["spent"] in (0, 2500)
    data = analysis(logged_in)
    assert data["needs"] == 2500 and data["take_home_income"] is None
    assert all(row["percent"] is None for row in data["split"])  # no income-based percentages
    goal_id = add_goal_with_money(logged_in)
    goals = logged_in.get("/api/goals").json()
    assert goals["monthly_target"] is None and goals["goals"][0]["status"] == "No target"  # no guessed "Needs more"
    assert goals["warning"] is None and goal_id


# ===== 3. INCOME + EXPENSES, NO LOANS =====
def test_income_and_expenses_but_no_loans(logged_in):
    add_income(logged_in)
    add_expense(logged_in, 3000)
    s = summary(logged_in)
    assert s["left_to_spend"] == 17000 and s["needs_percent"] == 15
    data = analysis(logged_in)
    assert data["remaining"] == 17000 and data["remaining_excludes_loans"] is True
    assert data["loan_repayments"] is None and "NO_LOANS" in data["data_gaps"]


# ===== 4. LOANS ONLY =====
def test_loan_but_no_income_or_expenses(logged_in, fake_groq):
    add_loan(logged_in, 1500)
    assert status(logged_in)["loans"] == "provided"
    loans = logged_in.get("/api/my-loans").json()
    assert loans["total_monthly_payment"] == 1500 and loans["loans"][0]["name"] == "Student loan"
    s = summary(logged_in)
    assert s["income"] is None and s["spent"] is None
    data = analysis(logged_in)
    assert data["loan_repayments"] == 1500 and data["take_home_income"] is None and data["enough_for_ai"] is True
    assert logged_in.post("/api/insights/generate", json={}).status_code == 200
    data_line = fake_groq["last_messages"][1]["content"].splitlines()[1]  # the JSON summary sent to the AI
    sent = json.loads(data_line)
    assert sent["loan_repayments"] == 1500 and sent["information_given"]["income"] == "missing"
    for unknown in ("take_home_income", "needs", "wants", "remaining", "saved_this_month", "bank_savings_balance"):
        assert unknown not in sent  # never sent as 0
    assert {"NO_INCOME", "NO_EXPENSES"} <= set(sent["missing_information"])


# ===== 5. SAVINGS ONLY =====
def test_savings_but_nothing_else(logged_in):
    add_goal_with_money(logged_in)
    assert status(logged_in) == {"income": "missing", "expenses": "missing", "loans": "missing", "savings": "provided"}
    savings = logged_in.get("/api/savings").json()
    assert savings["bank_balance"] is None  # adding to a goal doesn't invent a bank balance
    # No income and no own target → no monthly saving target, so Saved is unknown ("—"): the goal deposit is
    # money set aside from the bank, not this month's saving (was: 1000)
    assert savings["saved_this_month"] is None and savings["monthly_target"] is None
    s = summary(logged_in)
    assert s["saved"] is None and s["income"] is None and s["savings_percent"] is None
    assert analysis(logged_in)["savings"] is None


# ===== 7. ADDING MISSING INFORMATION LATER =====
def test_adding_information_later_turns_features_on(logged_in):
    assert summary(logged_in)["left_to_spend"] is None
    add_income(logged_in)
    assert summary(logged_in)["left_to_spend"] is None  # still no spending information
    add_expense(logged_in, 5000)
    s = summary(logged_in)
    assert s["left_to_spend"] == 15000 and s["needs_percent"] == 25
    assert logged_in.put("/api/savings", json={"bank_balance": 12000}).status_code == 200
    assert logged_in.get("/api/savings").json()["bank_balance"] == 12000
    add_loan(logged_in)
    assert status(logged_in) == {"income": "provided", "expenses": "provided", "loans": "provided",
                                 "savings": "provided"}


# ===== "I HAVE NONE" (= a real zero) =====
def test_saying_none_is_a_real_zero_and_can_be_undone(logged_in):
    for topic in ("income", "expenses", "loans", "savings"):
        res = logged_in.put("/api/info-choices", json={"topic": topic, "month": MONTH, "none": True})
        assert res.status_code == 200 and res.json()[topic] == "none"
    s = summary(logged_in)
    assert (s["income"], s["spent"], s["saved"], s["left_to_spend"]) == (0, 0, 0, 0)
    assert s["needs_percent"] is None  # still no % of a zero income
    assert analysis(logged_in)["loan_repayments"] == 0
    logged_in.put("/api/info-choices", json={"topic": "income", "month": MONTH, "none": False})
    assert status(logged_in)["income"] == "missing" and summary(logged_in)["income"] is None


def test_none_for_one_month_only(logged_in):
    logged_in.put("/api/info-choices", json={"topic": "income", "month": "2026-01", "none": True})
    assert logged_in.get("/api/info-status?month=2026-01").json()["income"] == "none"
    assert logged_in.get("/api/info-status?month=2026-02").json()["income"] == "missing"


def test_real_records_win_over_none(logged_in):
    logged_in.put("/api/info-choices", json={"topic": "loans", "none": True})
    add_loan(logged_in)
    assert status(logged_in)["loans"] == "provided"


# ===== 8 + 9. EDITING AND DELETING =====
def test_editing_and_deleting_updates_everything(logged_in):
    income_id = add_income(logged_in, 20000)
    expense_id = add_expense(logged_in, 4000)
    loan_id = add_loan(logged_in, 1000)
    assert analysis(logged_in)["remaining"] == 15000
    res = logged_in.put(f"/api/my-loans/{loan_id}", json={"balance": 30000, "annual_rate": 7, "monthly_payment": 2000})
    assert res.status_code == 200 and res.json()["total_monthly_payment"] == 2000
    assert analysis(logged_in)["remaining"] == 14000
    assert logged_in.delete(f"/api/my-loans/{loan_id}").status_code == 200
    assert status(logged_in)["loans"] == "missing" and analysis(logged_in)["loan_repayments"] is None
    assert logged_in.delete(f"/api/expenses/{expense_id}").status_code == 200
    assert summary(logged_in)["spent"] is None and summary(logged_in)["left_to_spend"] is None
    assert logged_in.delete(f"/api/income/{income_id}").status_code == 200
    assert summary(logged_in)["income"] is None
    assert logged_in.put("/api/savings", json={"bank_balance": None}).status_code == 200  # remove the balance
    assert logged_in.get("/api/savings").json()["bank_balance"] is None


# ===== VALIDATION (same rules as the Loans tab form) =====
def test_bad_loans_and_choices_are_rejected(logged_in):
    good = {"balance": 1000, "annual_rate": 5, "monthly_payment": 100}
    for change in ({"balance": 0}, {"balance": -5}, {"balance": 100_000_001}, {"annual_rate": 101},
                   {"annual_rate": -1}, {"monthly_payment": 0}, {"name": "x" * 61}, {"start_date": "soon"}):
        assert logged_in.post("/api/my-loans", json={**good, **change}).status_code == 422, change
    assert logged_in.get("/api/my-loans").json()["loans"] == []
    assert logged_in.put("/api/info-choices", json={"topic": "pets", "none": True}).status_code == 422
    assert logged_in.put("/api/info-choices", json={"topic": "income", "month": "2026-13", "none": True}).status_code == 422


def test_other_user_cannot_touch_my_loans(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    loan_id = add_loan(asha)
    ravi = log_in(new_client(), sent_codes, "ravi@example.com")
    assert ravi.get("/api/my-loans").json()["loans"] == []
    body = {"balance": 1, "annual_rate": 1, "monthly_payment": 1}
    assert ravi.put(f"/api/my-loans/{loan_id}", json=body).status_code == 404
    assert ravi.delete(f"/api/my-loans/{loan_id}").status_code == 404
    assert status(ravi)["loans"] == "missing" and status(asha)["loans"] == "provided"


# ===== 11. EXISTING USERS KEEP THEIR DATA (migration 0006) =====
def test_migration_keeps_existing_savings(tmp_path):
    database.connect(f"sqlite:///{tmp_path.as_posix()}/old.db")
    config = Config(str(database.BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(database.BACKEND_DIR / "migrations"))
    config.attributes["engine"] = database.engine
    command.upgrade(config, "0005")  # the database as it was before this change
    with database.engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id, email, password_hash, failed_attempts, is_locked, created_at) "
                                   "VALUES (:id, 'old@example.com', 'x', 0, 0, '2026-01-01')"), {"id": "a" * 32})
        connection.execute(sa.text("INSERT INTO savings_settings (id, user_id, bank_balance_cents, safety_net_saved_cents) "
                                   "VALUES (:id, :user, 0, 500)"), {"id": "b" * 32, "user": "a" * 32})
    command.upgrade(config, "head")
    with database.engine.begin() as connection:
        row = connection.execute(sa.text("SELECT bank_balance_cents, safety_net_saved_cents FROM savings_settings")).one()
    assert tuple(row) == (0, 500)  # an existing Rs 0 balance stays exactly as the user had it
    database.engine.dispose()
    assert Path(tmp_path / "old.db").exists()
