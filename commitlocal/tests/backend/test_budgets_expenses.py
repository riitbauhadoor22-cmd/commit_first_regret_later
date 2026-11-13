# test_budgets_expenses.py — tests for the category budget + expense routes used by the Money out category pop-up:
# set/update budgets (incl. the /api/budget alias), bad input, add/edit/delete, month + category filter, other users.
import pytest

from conftest import log_in


# ===== BUDGETS =====
def test_set_and_update_budget_applies_every_month(logged_in):
    logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 5000})
    res = logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 4500})
    assert res.status_code == 200 and len(res.json()) == 1  # updated, not duplicated
    for month in ["2025-01", "2030-12"]:  # same budget in any month
        budgets = logged_in.get(f"/api/budgets?month={month}").json()
        assert [(b["category"], b["monthly_limit"]) for b in budgets] == [("Groceries", 4500)]
    rows = logged_in.get("/api/summary?month=2025-01").json()["categories"]
    assert next(r for r in rows if r["category"] == "Groceries")["budget"] == 4500


def test_singular_budget_alias_works(logged_in):
    assert logged_in.put("/api/budget", json={"category": "Transport", "monthly_limit": 800}).status_code == 200
    assert logged_in.get("/api/budget").json()[0]["monthly_limit"] == 800


def test_budget_bad_input(logged_in):
    assert logged_in.put("/api/budgets", json={"category": "Rockets", "monthly_limit": 100}).status_code == 422
    for limit in [0, -5, "", "abc"]:
        assert logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": limit}).status_code == 422
    assert logged_in.get("/api/budgets?month=2025-13").status_code == 422
    assert logged_in.get("/api/budgets").json() == []


# ===== EXPENSES =====
@pytest.mark.parametrize("amount", [-1, 0, "", None])
def test_bad_expense_amount_has_clear_message(logged_in, amount):
    res = logged_in.post("/api/expenses", json={"amount": amount, "category": "Groceries"})
    assert res.status_code == 422
    assert res.json()["detail"][0]["msg"]  # a message the app can show


def test_missing_amount_and_bad_category(logged_in):
    assert logged_in.post("/api/expenses", json={"category": "Groceries"}).status_code == 422
    res = logged_in.post("/api/expenses", json={"amount": 10, "category": "Rockets"})
    assert res.status_code == 422 and "Pick one of" in res.json()["detail"][0]["msg"]


def test_add_edit_delete_updates_category_row(logged_in):
    logged_in.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 5000})
    eid = logged_in.post("/api/expenses", json={"amount": 3200, "category": "Groceries", "note": "veg",
                                                "date": "2025-03-10"}).json()["id"]
    row = lambda: next(r for r in logged_in.get("/api/summary?month=2025-03").json()["categories"]
                       if r["category"] == "Groceries")
    assert (row()["spent"], row()["over_by"]) == (3200, 0)

    res = logged_in.put(f"/api/expenses/{eid}", json={"amount": 5700, "category": "Groceries", "note": "big shop",
                                                       "date": "2025-03-11"})
    assert res.status_code == 200 and res.json()["note"] == "big shop" and res.json()["date"] == "2025-03-11"
    assert (row()["spent"], row()["over_by"]) == (5700, 700)

    assert logged_in.delete(f"/api/expenses/{eid}").status_code == 200
    assert row()["spent"] == 0


def test_filter_by_month_and_category_newest_first(logged_in):
    add = lambda amount, category, date: logged_in.post(
        "/api/expenses", json={"amount": amount, "category": category, "date": date})
    add(100, "Groceries", "2025-03-01")
    add(200, "Groceries", "2025-03-20")
    add(300, "Transport", "2025-03-05")
    add(400, "Groceries", "2025-04-02")
    data = logged_in.get("/api/expenses?month=2025-03&category=Groceries").json()
    assert [e["amount"] for e in data["everyday"]] == [200, 100]  # newest first, only March Groceries
    assert len(logged_in.get("/api/expenses?month=2025-03").json()["everyday"]) == 3
    assert logged_in.get("/api/expenses?month=2025-03&category=Rockets").status_code == 422


def test_fixed_bill_shows_in_its_category_filter(logged_in):
    logged_in.post("/api/expenses", json={"amount": 499, "category": "Subscriptions", "date": "2025-01-05",
                                          "is_fixed": True})
    data = logged_in.get("/api/expenses?month=2025-06&category=Subscriptions").json()
    assert data["everyday"] == [] and [e["amount"] for e in data["fixed"]] == [499]
    assert logged_in.get("/api/expenses?month=2025-06&category=Groceries").json()["fixed"] == []


# ===== OTHER USERS =====
def test_other_user_cannot_touch_budgets_or_expenses(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    ben = log_in(new_client(), sent_codes, "ben@example.com")
    asha.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 5000})
    eid = asha.post("/api/expenses", json={"amount": 99, "category": "Groceries"}).json()["id"]

    assert ben.get("/api/budgets").json() == []
    assert ben.get("/api/expenses?category=Groceries").json()["everyday"] == []
    assert ben.put(f"/api/expenses/{eid}", json={"amount": 1, "category": "Groceries"}).status_code == 404
    assert ben.delete(f"/api/expenses/{eid}").status_code == 404
    ben.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 1})  # Ben's own budget
    ben.put("/api/budgets", json={"category": "Groceries", "monthly_limit": None})  # removes only Ben's

    assert asha.get("/api/budgets").json()[0]["monthly_limit"] == 5000
    assert asha.get("/api/expenses").json()["everyday"][0]["amount"] == 99
