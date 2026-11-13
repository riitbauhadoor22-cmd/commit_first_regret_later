# test_error_codes.py — every error reply has a "code" the frontend translates (backend/errors.py),
# and still keeps "detail" (the English message / Pydantic list) as before.
import uuid

import pytest
from conftest import PASSWORD, register


# ===== FORM (422) ERRORS =====
@pytest.mark.parametrize("amount", [-1, 0, 10 ** 12])
def test_bad_amount_gives_invalid_amount(logged_in, amount):
    res = logged_in.post("/api/expenses", json={"amount": amount, "category": "Groceries"})
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "INVALID_AMOUNT"
    assert body["detail"][0]["msg"]  # the old list is still there


def test_bad_category_and_missing_amount(logged_in):
    res = logged_in.post("/api/expenses", json={"amount": 10, "category": "Rockets"})
    assert res.json()["code"] == "INVALID_CATEGORY"
    res = logged_in.post("/api/expenses", json={"category": "Groceries"})
    assert res.json()["code"] == "INVALID_AMOUNT"  # missing amount → the amount message


def test_loan_form_codes(logged_in):
    good = {"monthly_income": 30000}
    assert logged_in.post("/api/loans/predict", json={**good, "years": 0}).json()["code"] == "INVALID_YEARS"
    assert logged_in.post("/api/loans/predict", json={"monthly_income": -1}).json()["code"] == "INVALID_INCOME"


# ===== OUR OWN ERRORS =====
def test_not_logged_in_code(client):
    res = client.get("/api/summary")
    assert res.status_code == 401
    assert res.json()["code"] == "NOT_LOGGED_IN"


def test_wrong_password_has_code_and_attempts_left(client, sent_codes):
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD + "x"})
    body = res.json()
    assert res.status_code == 401
    assert body["code"] == "WRONG_LOGIN_TRIES" and body["params"] == {"left": 2}
    assert "Wrong email or password" in body["detail"]  # English message kept


def test_not_found_and_success_codes(logged_in):
    res = logged_in.put(f"/api/goals/{uuid.uuid4()}",
                        json={"name": "Phone", "target_amount": 100, "deadline": "2030-01-01"})
    assert res.status_code == 404 and res.json()["code"] == "GOAL_NOT_FOUND"
    assert logged_in.post("/api/auth/logout").json()["code"] == "LOGGED_OUT"
