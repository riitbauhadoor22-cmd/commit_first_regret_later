# test_savings_model.py — the three savings values (bank_savings_balance, monthly_saving_target, saved_this_month)
# and the ONE shared month maths (services/month_summary.py). Test data = the user's screen:
# income Rs 2,000 · spending Rs 32 (Rs 12 + Rs 20) · monthly saving target Rs 100 · bank balance Rs 2,000,000.
import json
from datetime import date

from money import get_this_month
from services.month_summary import build_month_summary, build_split, get_saving_progress

MONTH = "2026-11"
TODAY = date(2026, 11, 14)  # November has 30 days
INCOMES = [{"amount": 2000, "frequency": "monthly", "date": "2026-11-01"}]
EXPENSES = [
    {"amount": 12, "category": "Groceries", "kind": "need", "is_fixed": False, "date": "2026-11-14", "note": ""},
    {"amount": 20, "category": "Transport", "kind": "need", "is_fixed": False, "date": "2026-11-14", "note": ""},
]
ALL_GIVEN = {"income": "provided", "expenses": "provided", "loans": "none", "savings": "provided"}


def month(savings=None, incomes=INCOMES, expenses=EXPENSES, loans=(), info=ALL_GIVEN):
    savings = savings or {"monthly_target": 100, "bank_balance": 2_000_000, "safety_net_saved": 2000}
    return build_month_summary(incomes, expenses, list(loans), savings, info, MONTH, TODAY)


# ===== SUMMARY CARD + SPLIT + FORECAST (test data) =====
def test_test_data_gives_the_right_card():
    s = month()
    assert (s["income"], s["out"], s["saved"], s["left_to_spend"]) == (2000, 32, 100, 1868)
    assert s["left_reason"] is None
    assert round(s["needs_percent"]) == 2 and s["wants_percent"] == 0 and s["savings_percent"] == 5.0
    bar = s["split"]["bar"]
    assert sum(bar.values()) <= 100.01 and bar["unplanned"] > 90  # grey "not planned yet" rest
    assert s["split"]["percent"]["unplanned"] == 93.4


def test_forecast_is_on_track_not_short():
    f = month()["forecast"]
    assert f["available"] and f["forecast_spent"] == 68.57  # 32 ÷ 14 days × 30
    assert f["planned_savings"] == 100
    assert f["left_at_month_end"] == 1831.43 and f["left_at_month_end"] > 0  # "on track", never "short"


def test_bank_balance_never_changes_the_month():
    base = month()
    for balance in (None, 0, 2_000_000, 999_999_999):
        other = month({"monthly_target": 100, "bank_balance": balance, "safety_net_saved": 2000})
        for key in ("income", "out", "saved", "left_to_spend", "split", "forecast"):
            assert other[key] == base[key], key


# ===== MONTHLY SAVING CARD =====
def test_saving_progress():
    assert get_saving_progress(100, 100) == {"state": "ok", "percent": 100.0, "reached": True, "extra": 0}
    over = get_saving_progress(150, 100)
    assert over["percent"] == 100.0 and over["reached"] and over["extra"] == 50  # bar capped, "Target reached"
    assert get_saving_progress(50, 100)["percent"] == 50 and not get_saving_progress(50, 100)["reached"]
    for target in (0, None):  # "Set a monthly saving target", never ÷ 0
        assert get_saving_progress(100, target)["state"] == "no_target"


# ===== EDGE CASES =====
def test_income_zero_has_no_division_and_no_nan():
    s = month(incomes=[], info={**ALL_GIVEN, "income": "none"})  # "No income this month"
    assert s["income"] == 0 and s["split"] is None
    assert s["needs_percent"] is None and s["wants_percent"] is None and s["savings_percent"] is None
    assert s["left_to_spend"] == -132  # 0 − 32 − 100
    assert "NaN" not in json.dumps(s) and "Infinity" not in json.dumps(s)
    assert build_split(0, 0, 0, 0, 0) is None


def test_negative_left_to_spend_has_a_reason():
    small = [{"amount": 100, "frequency": "monthly", "date": "2026-11-01"}]
    s = month(incomes=small)
    assert s["left_to_spend"] == -32 and s["left_reason"] == "SAVING_AND_SPENDING"
    s = month(incomes=small, expenses=EXPENSES * 4, info={**ALL_GIVEN, "savings": "none"})  # not saving
    assert s["saved"] == 0 and s["left_to_spend"] == -28 and s["left_reason"] == "SPENDING"


def test_split_never_goes_over_100():
    split = build_split(1000, 900, 400, 200, 0)
    assert split["over_income"] and abs(sum(split["bar"].values()) - 100) < 0.05
    assert split["percent"]["needs"] == 90 and split["bar"]["unplanned"] == 0


def test_loans_counted_once():
    loan = {"monthly_payment": 500, "start_date": "2026-11-01", "created_at": "2026-11-01 10:00"}
    assert month(loans=[loan], info={**ALL_GIVEN, "loans": "provided"})["out"] == 532
    bill = {"amount": 500, "category": "Bills", "kind": "need", "is_fixed": True, "date": "2026-11-01", "note": ""}
    s = month(expenses=EXPENSES + [bill], loans=[loan], info={**ALL_GIVEN, "loans": "provided"})
    assert s["out"] == 532 and s["loan_repayments"] == 0  # the loan is already the fixed bill
    assert month(loans=[loan], info={**ALL_GIVEN, "loans": "missing"})["out"] == 32  # not shared → left out


# ===== THROUGH THE API (same numbers everywhere) =====
def test_api_test_user(logged_in):
    this_month = get_this_month()
    assert logged_in.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 2000, "frequency": "monthly",
                                               "date": this_month + "-01"}).status_code == 201
    for amount in (12, 20):
        assert logged_in.post("/api/expenses", json={"amount": amount, "category": "Groceries",
                                                     "date": this_month + "-01"}).status_code == 201
    assert logged_in.put("/api/savings", json={"bank_balance": 2_000_000, "monthly_target": 100}).status_code == 200
    before = logged_in.get("/api/summary").json()
    # Adding to the safety net and changing the bank balance must not change In / Out / Saved / Left
    savings = logged_in.post("/api/savings/safety-net/add-money", json={"amount": 2000}).json()
    assert savings["bank_balance"] == 2_000_000  # set aside inside the balance, not new money
    assert savings["saved_this_month"] == 100 and savings["saving_progress"]["percent"] == 100
    assert {p["label"]: p["amount"] for p in savings["bank_bar"]}["Free"] == 1_998_000
    assert logged_in.put("/api/savings", json={"bank_balance": 20_000_000, "monthly_target": 100}).status_code == 200
    after = logged_in.get("/api/summary").json()
    for s in (before, after):
        assert (s["income"], s["out"], s["saved"], s["left_to_spend"], s["savings_percent"]) == (2000, 32, 100, 1868, 5)
    dash = logged_in.get("/api/dashboard").json()
    assert dash["balance"]["balance"] == 1868 and dash["recap"]["savings"] == 100
    insights = logged_in.get(f"/api/insights?month={this_month}").json()["analysis"]
    assert insights["savings"] == 100 and insights["remaining"] == 1868
