# test_money.py — tests for adding expenses (incl. bad amounts) and the overall monthly budget.
import datetime

import pytest

TODAY = datetime.date.today().isoformat()


# ===== EXPENSES =====
def test_add_expense_and_list_it(logged_in):
    res = logged_in.post("/api/expenses", json={"amount": 245, "category": "Food & drinks", "note": "lunch"})
    assert res.status_code == 201
    data = logged_in.get("/api/expenses").json()
    assert data["total"] == 245
    assert data["expenses"][0]["note"] == "lunch"
    assert data["expenses"][0]["date"] == TODAY  # date defaults to today
    assert data["expenses"][0]["kind"] == "want"


def test_expense_with_own_date_goes_in_that_month(logged_in):
    logged_in.post("/api/expenses", json={"amount": 100, "category": "Transport", "date": "2025-01-15"})
    assert logged_in.get("/api/expenses?month=2025-01").json()["total"] == 100


@pytest.mark.parametrize("amount", [0, -50, None, "", 10_000_001])
def test_bad_expense_amounts_are_rejected(logged_in, amount):
    res = logged_in.post("/api/expenses", json={"amount": amount, "category": "Other"})
    assert res.status_code == 422
    assert logged_in.get("/api/expenses").json()["expenses"] == []


def test_missing_amount_is_rejected(logged_in):
    assert logged_in.post("/api/expenses", json={"category": "Other"}).status_code == 422


def test_unknown_category_is_rejected(logged_in):
    assert logged_in.post("/api/expenses", json={"amount": 10, "category": "Rockets"}).status_code == 400


def test_expenses_need_login(client):
    assert client.post("/api/expenses", json={"amount": 10, "category": "Other"}).status_code == 401
    assert client.get("/api/expenses").status_code == 401


# ===== BUDGET =====
def test_no_budget_yet(logged_in):
    data = logged_in.get("/api/budget").json()
    assert data["monthly_limit"] is None
    assert data["spent"] == 0


def test_set_budget_and_see_spent(logged_in):
    assert logged_in.put("/api/budget", json={"monthly_limit": 5000}).status_code == 200
    logged_in.post("/api/expenses", json={"amount": 1200, "category": "Groceries"})
    data = logged_in.get("/api/budget").json()
    assert data == {"month": TODAY[:7], "monthly_limit": 5000, "spent": 1200, "over_by": 0}


def test_budget_can_be_changed_and_shows_over_by(logged_in):
    logged_in.put("/api/budget", json={"monthly_limit": 5000})
    logged_in.put("/api/budget", json={"monthly_limit": 1000})
    logged_in.post("/api/expenses", json={"amount": 1500, "category": "Shopping"})
    data = logged_in.get("/api/budget").json()
    assert data["monthly_limit"] == 1000
    assert data["over_by"] == 500


@pytest.mark.parametrize("limit", [0, -100, None, "", 10_000_001])
def test_bad_budget_amounts_are_rejected(logged_in, limit):
    assert logged_in.put("/api/budget", json={"monthly_limit": limit}).status_code == 422


def test_budget_needs_login(client):
    assert client.put("/api/budget", json={"monthly_limit": 100}).status_code == 401
