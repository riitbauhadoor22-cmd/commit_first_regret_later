# test_security_db.py — proves the database rules: one user can never read, edit or delete another
# user's data; deleting a user deletes all their rows (ON DELETE CASCADE); amounts can't be negative (CHECK).
import datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

import database
from conftest import log_in
from models import Budget, Deposit, Expense, Income, SavingsGoal, User

NEXT_YEAR = f"{datetime.date.today().year + 1}-12-31"
TODAY = datetime.date.today().isoformat()


# ===== FIXTURES =====
@pytest.fixture
def two_users(new_client, sent_codes):
    """Asha owns some data; Ben is a second logged-in user in another "browser"."""
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    ben = log_in(new_client(), sent_codes, "ben@example.com")
    ids = {
        "expense": asha.post("/api/expenses", json={"amount": 99, "category": "Other", "note": "secret"}).json()["id"],
        "income": asha.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 5000,
                                                 "frequency": "monthly", "date": TODAY}).json()["id"],
        "goal": asha.post("/api/goals", json={"name": "Bike", "target_amount": 900,
                                              "deadline": NEXT_YEAR}).json()["goals"][0]["id"],
    }
    asha.put("/api/budgets", json={"category": "Groceries", "monthly_limit": 300})
    asha.post("/api/savings/safety-net/add-money", json={"amount": 50})
    return asha, ben, ids


# ===== ONE USER CAN'T SEE ANOTHER'S DATA =====
def test_other_user_sees_nothing(two_users):
    _, ben, _ = two_users
    assert ben.get("/api/expenses").json()["everyday"] == []
    assert ben.get("/api/income").json()["regular"] == []
    assert ben.get("/api/budgets").json() == []
    assert ben.get("/api/goals").json()["goals"] == []
    assert ben.get("/api/expenses/quick").json() == []
    summary = ben.get("/api/summary").json()
    assert (summary["spent"], summary["income"], summary["saved"]) == (0, 0, 0)
    assert ben.get("/api/savings").json()["bank_balance"] == 0


def test_other_user_cannot_edit_or_delete(two_users):
    asha, ben, ids = two_users
    assert ben.put(f"/api/expenses/{ids['expense']}", json={"amount": 1, "category": "Other"}).status_code == 404
    assert ben.delete(f"/api/expenses/{ids['expense']}").status_code == 404
    assert ben.put(f"/api/income/{ids['income']}", json={"name": "X", "type": "Other", "amount": 1,
                                                       "frequency": "one-off", "date": TODAY}).status_code == 404
    assert ben.delete(f"/api/income/{ids['income']}").status_code == 404
    assert ben.put(f"/api/goals/{ids['goal']}", json={"name": "X", "target_amount": 1,
                                                    "deadline": NEXT_YEAR}).status_code == 404
    assert ben.delete(f"/api/goals/{ids['goal']}").status_code == 404
    assert ben.post(f"/api/goals/{ids['goal']}/add-money", json={"amount": 10}).status_code == 404

    # Asha's data is unchanged
    assert asha.get("/api/expenses").json()["everyday"][0]["amount"] == 99
    assert asha.get("/api/income").json()["regular"][0]["name"] == "Job"
    assert asha.get("/api/goals").json()["goals"][0]["saved_amount"] == 0


def test_bad_ids_are_rejected(logged_in):
    assert logged_in.delete("/api/expenses/1").status_code == 422  # ids must be UUIDs
    assert logged_in.delete("/api/expenses/1 OR 1=1").status_code == 422


# ===== DATABASE RULES =====
def test_deleting_a_user_deletes_all_their_rows(two_users):
    with database.open_db() as db:
        db.execute(delete(User).where(User.email == "asha@example.com"))
    with database.open_db() as db:
        for table in (Expense, Income, Budget, SavingsGoal, Deposit):
            assert db.scalar(select(func.count()).select_from(table)) == 0


@pytest.mark.parametrize("table, values", [
    (Expense, {"category": "Other", "kind": "need", "date": datetime.date.today()}),
    (Income, {"name": "X", "source": "Other", "frequency": "one-off", "date": datetime.date.today()}),
    (Deposit, {"date": datetime.date.today()}),
])
def test_negative_amounts_are_blocked_by_the_database(logged_in, table, values):
    with database.open_db() as db:
        user_id = db.scalar(select(User.id))
    with pytest.raises(IntegrityError):
        with database.open_db() as db:
            db.add(table(user_id=user_id, amount_cents=-100, **values))
