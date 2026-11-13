# test_money.py — tests for the money routes: expenses (incl. bad amounts), budgets, income, savings, goals,
# and that money is saved as whole cents with UUID ids.
import datetime
import uuid

import pytest
from sqlalchemy import select

import database
from models import Expense

TODAY = datetime.date.today().isoformat()
NEXT_YEAR = f"{datetime.date.today().year + 1}-12-31"


# ===== EXPENSES =====
def test_add_expense_and_list_it(logged_in):
    res = logged_in.post("/api/expenses", json={"amount": 245, "category": "Food & drinks", "note": "lunch"})
    assert res.status_code == 201
    uuid.UUID(res.json()["id"])  # ids are UUIDs, not 1, 2, 3
    data = logged_in.get("/api/expenses").json()
    first = data["everyday"][0]
    assert (first["amount"], first["note"], first["date"], first["kind"]) == (245, "lunch", TODAY, "want")


def test_money_is_stored_in_cents(logged_in):
    logged_in.post("/api/expenses", json={"amount": 150.50, "category": "Other"})
    with database.open_db() as db:
        assert db.scalar(select(Expense.amount_cents)) == 15050
    assert logged_in.get("/api/summary").json()["spent"] == 150.5


def test_expense_with_own_date_goes_in_that_month(logged_in):
    logged_in.post("/api/expenses", json={"amount": 100, "category": "Transport", "date": "2025-01-15"})
    assert logged_in.get("/api/summary?month=2025-01").json()["spent"] == 100
    assert logged_in.get("/api/expenses").json()["everyday"] == []


@pytest.mark.parametrize("amount", [0, -50, None, "", 10_000_001])
def test_bad_expense_amounts_are_rejected(logged_in, amount):
    res = logged_in.post("/api/expenses", json={"amount": amount, "category": "Other"})
    assert res.status_code == 422
    assert logged_in.get("/api/expenses").json()["everyday"] == []


def test_unknown_category_is_rejected(logged_in):
    assert logged_in.post("/api/expenses", json={"amount": 10, "category": "Rockets"}).status_code == 422


def test_edit_and_delete_expense(logged_in):
    expense_id = logged_in.post("/api/expenses", json={"amount": 10, "category": "Other"}).json()["id"]
    res = logged_in.put(f"/api/expenses/{expense_id}", json={"amount": 20, "category": "Bills", "is_fixed": True})
    assert res.json()["amount"] == 20 and res.json()["is_fixed"] == 1
    assert logged_in.delete(f"/api/expenses/{expense_id}").status_code == 200
    assert logged_in.delete(f"/api/expenses/{expense_id}").status_code == 404


def test_money_routes_need_login(client):
    assert client.post("/api/expenses", json={"amount": 10, "category": "Other"}).status_code == 401
    for path in ["/api/expenses", "/api/income", "/api/budgets", "/api/savings", "/api/goals", "/api/summary"]:
        assert client.get(path).status_code == 401


# ===== BUDGETS =====
def test_set_change_and_remove_budget(logged_in):
    logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 5000})
    budgets = logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 1000}).json()
    assert [(b["category"], b["monthly_limit"]) for b in budgets] == [("Groceries", 1000)]
    assert logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": None}).json() == []


@pytest.mark.parametrize("limit", [0, -100, "", 10_000_001])
def test_bad_budget_amounts_are_rejected(logged_in, limit):
    assert logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": limit}).status_code == 422


# ===== INCOME, SAVINGS, GOALS =====
def test_income_counts_in_summary(logged_in):
    res = logged_in.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 20000,
                                              "frequency": "monthly", "date": TODAY})
    assert res.status_code == 201
    assert logged_in.get("/api/summary").json()["income"] == 20000
    assert logged_in.get("/api/income").json()["regular"][0]["type"] == "Salary"


def test_savings_and_safety_net(logged_in):
    assert logged_in.put("/api/savings", json={"bank_balance": 1000, "monthly_target": 500}).status_code == 200
    data = logged_in.post("/api/savings/safety-net/add-money", json={"amount": 250.25}).json()
    assert data["bank_balance"] == 1250.25
    assert data["saved_this_month"] == 250.25


def test_goal_add_money_never_goes_past_target(logged_in):
    data = logged_in.post("/api/goals", json={"name": "Phone", "target_amount": 1000, "deadline": NEXT_YEAR}).json()
    goal_id = data["goals"][0]["id"]
    res = logged_in.post(f"/api/goals/{goal_id}/add-money", json={"amount": 1500}).json()
    assert res["added"] == 1000
    assert res["goals"][0]["status"] == "Done"
    assert logged_in.post(f"/api/goals/{goal_id}/add-money", json={"amount": 1}).status_code == 400
    assert logged_in.delete(f"/api/goals/{goal_id}").json()["goals"] == []
