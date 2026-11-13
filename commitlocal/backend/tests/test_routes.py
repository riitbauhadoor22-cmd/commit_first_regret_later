# tests/test_routes.py — tries the money API the way the app will use it (temporary database, fake login).
from money import get_this_month, get_today


def test_money_routes_need_login(tmp_path, monkeypatch):
    import database
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.create_tables()
    assert TestClient(app).get("/api/summary").status_code == 401


def test_add_income_and_expense_shows_in_summary(client):
    month = get_this_month()
    assert client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 10000,
                                            "frequency": "monthly", "date": f"{month}-01"}).status_code == 201
    r = client.post("/api/expenses", json={"amount": 245, "category": "Food & drinks", "note": "lunch"})
    assert r.status_code == 201
    assert r.json()["kind"] == "want"        # default from the category
    assert r.json()["date"] == get_today()   # default date

    s = client.get(f"/api/summary?month={month}").json()
    assert s["income"] == 10000 and s["spent"] == 245 and s["left_to_spend"] == 9755


def test_bad_amounts_are_rejected(client):
    assert client.post("/api/expenses", json={"amount": 0, "category": "Other"}).status_code == 422
    assert client.post("/api/expenses", json={"amount": -5, "category": "Other"}).status_code == 422
    assert client.post("/api/expenses", json={"amount": 5, "category": "Pizza"}).status_code == 422


def test_quick_add_logs_the_chip_again_today(client):
    for _ in range(2):
        client.post("/api/expenses", json={"amount": 38, "category": "Transport", "note": "Bus"})
    chips = client.get("/api/expenses/quick").json()
    assert chips[0]["label"] == "Bus Rs 38"
    r = client.post("/api/expenses/quick", json={"note": "Bus", "amount": 38})
    assert r.status_code == 201 and r.json()["source"] == "quick"


def test_budget_set_and_remove(client):
    client.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 3000})
    assert client.get("/api/budgets").json()[0]["monthly_limit"] == 3000
    client.put("/api/budgets", json={"category": "Groceries", "monthly_limit": None})
    assert client.get("/api/budgets").json() == []


def test_add_money_to_goal_updates_goal_and_bank(client):
    client.post("/api/goals", json={"name": "Phone", "target_amount": 1000, "deadline": "2030-01-01", "priority": 1})
    goal_id = client.get("/api/goals").json()["goals"][0]["id"]

    r = client.post(f"/api/goals/{goal_id}/add-money", json={"amount": 5000})
    assert r.json()["added"] == 1000                 # capped at the target
    assert r.json()["goals"][0]["saved_amount"] == 1000
    assert client.get("/api/savings").json()["bank_balance"] == 1000
    assert client.post(f"/api/goals/{goal_id}/add-money", json={"amount": 10}).status_code == 400


def test_safety_net_add_money(client):
    r = client.post("/api/savings/safety-net/add-money", json={"amount": 500}).json()
    assert r["safety_net"]["saved"] == 500 and r["bank_balance"] == 500 and r["saved_this_month"] == 500


def test_cannot_touch_another_users_rows(client):
    import database
    with database.open_db() as db:
        db.execute("INSERT INTO expenses (user_id, amount, category, kind, date) VALUES (2, 50, 'Other', 'need', '2026-11-01')")
    assert client.delete("/api/expenses/1").status_code == 404


def test_income_list_splits_regular_and_one_off(client):
    month = get_this_month()
    client.post("/api/income", json={"name": "Tutoring", "type": "Side hustle", "amount": 600,
                                     "frequency": "weekly", "date": f"{month}-01"})
    client.post("/api/income", json={"name": "Birthday gift", "type": "Other", "amount": 1000,
                                     "frequency": "one-off", "date": f"{month}-02"})
    data = client.get(f"/api/income?month={month}").json()
    assert [i["name"] for i in data["regular"]] == ["Tutoring"]
    assert data["regular"][0]["per_month"] == 2600
    assert [i["name"] for i in data["one_off"]] == ["Birthday gift"]
    assert "Salary" in data["types"]
    next_month = client.get("/api/income?month=2099-01").json()
    assert next_month["one_off"] == [] and len(next_month["regular"]) == 1  # added once, counted every month


def test_edit_and_delete_income(client):
    r = client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 100,
                                         "frequency": "monthly", "date": "2026-01-01"}).json()
    edited = client.put(f"/api/income/{r['id']}", json={"name": "Job", "type": "Salary", "amount": 200,
                                                         "frequency": "monthly", "date": "2026-01-01"}).json()
    assert edited["amount"] == 200
    assert client.delete(f"/api/income/{r['id']}").status_code == 200
    assert client.delete(f"/api/income/{r['id']}").status_code == 404
    assert client.post("/api/income", json={"name": "X", "type": "Lottery", "amount": 5,
                                            "frequency": "monthly", "date": "2026-01-01"}).status_code == 422
