# test_month_recap.py — the month-end recap of LAST month: shown once (profiles.recap_seen_month), worked out from
# the data, "Move Rs X to savings?" only when something is left over, no left-over line without income.
from money import get_this_month
from routes.month_recap import last_day_of
from services.financial_analysis import get_previous_month

RECAP = "/api/month-recap"
LAST = get_previous_month(get_this_month())


def add_last_month(client, income=10000, spent=4000.4, saved=1000):
    if income:
        assert client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": income,
                                                "frequency": "one-off", "date": LAST + "-01"}).status_code == 201
    assert client.post("/api/expenses", json={"amount": spent, "category": "Groceries",
                                              "date": LAST + "-10"}).status_code == 201
    if saved:
        assert client.post("/api/savings/entries", json={"kind": "deposit", "amount": saved, "place": "general",
                                                         "date": LAST + "-15"}).status_code == 201


def test_recap_shows_once(logged_in):
    assert logged_in.get(RECAP).json()["show"] is False  # nothing recorded last month: no recap
    add_last_month(logged_in)
    recap = logged_in.get(RECAP).json()
    assert recap["show"] is True and recap["month"] == LAST
    assert (recap["saved"], recap["total_savings"], recap["left_over"], recap["move_amount"]) == (1000, 1000,
                                                                                              4999.6, 4999)
    assert logged_in.post(RECAP + "/seen").status_code == 200
    assert logged_in.get(RECAP).json()["show"] is False  # seen: not again this month


def test_yes_moves_left_over_as_last_months_saving(logged_in):
    add_last_month(logged_in)
    data = logged_in.post(RECAP + "/move").json()
    assert data["moved"] == 4999 and data["bank_balance"] == 5999
    assert data["entry"]["date"] == last_day_of(LAST).isoformat() and data["entry"]["source"] == "income"
    last = logged_in.get("/api/summary", params={"month": LAST}).json()
    assert last["saved"] == 5999 and 0 <= last["left_to_spend"] < 1
    recap = logged_in.get(RECAP).json()
    assert recap["show"] is False and recap["move_amount"] is None  # seen, and nothing left to move twice
    assert logged_in.post(RECAP + "/move").json()["code"] == "NOTHING_LEFT"


def test_no_left_over_no_button(logged_in):
    add_last_month(logged_in, income=5000, spent=5000, saved=0)
    recap = logged_in.get(RECAP).json()
    assert recap["show"] is True and recap["left_over"] == 0 and recap["move_amount"] is None
    assert logged_in.post(RECAP + "/move").status_code == 400


def test_no_income_no_left_over_line(logged_in):
    add_last_month(logged_in, income=0, saved=0)
    recap = logged_in.get(RECAP).json()
    assert recap["show"] is True and recap["left_over"] is None and recap["move_amount"] is None


def test_recap_needs_login(client):
    assert client.get(RECAP).status_code == 401 and client.post(RECAP + "/move").status_code == 401
