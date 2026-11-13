# test_loans.py — POST /api/loans/predict: model answer, validation, 40% rule fallback, login required.
from pathlib import Path

import pytest

import routes.loans
from models import CREDIT_SCORE_MAX, CREDIT_SCORE_MIN

URL = "/api/loans/predict"
GOOD = {"monthly_income": 60000, "monthly_expenses": 30000, "existing_debt_payment": 6000,
        "credit_score": 700, "age": 30, "interest_rate": 10, "years": 5}


# ===== HELPERS =====
def with_changes(**changes):
    return {**GOOD, **changes}


# ===== TESTS =====
def test_valid_input_returns_numbers(logged_in):
    res = logged_in.post(URL, json=GOOD)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["predicted_max_loan"], float) and data["predicted_max_loan"] >= 0
    assert data["debt_to_income_ratio"] == 0.1  # 6000 / 60000, as a fraction
    assert data["verdict"] == "Good to borrow"
    # 40% rule: 24000 − 6000 = Rs 18,000 a month, 60 months at 10% a year
    assert data["formula_monthly_payment"] == 18000
    assert data["formula_max_loan"] == pytest.approx(847 * 1000, rel=0.01)
    if routes.loans.loan_model is not None:
        assert data["source"] == "ai"


@pytest.mark.parametrize("ratio_debt, verdict", [(18000, "Borrow carefully"), (24000, "Borrow carefully"),
                                                  (30000, "Not recommended right now")])
def test_verdicts(logged_in, ratio_debt, verdict):
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=ratio_debt)).json()
    assert data["verdict"] == verdict
    assert data["predicted_max_loan"] >= 0 and data["formula_max_loan"] >= 0  # never negative


@pytest.mark.parametrize("changes", [
    {"monthly_income": 0}, {"monthly_income": -5}, {"monthly_expenses": -1}, {"existing_debt_payment": -1},
    {"credit_score": CREDIT_SCORE_MIN - 1}, {"credit_score": CREDIT_SCORE_MAX + 1},
    {"age": 17}, {"age": 101}, {"monthly_income": 10 ** 12}, {"years": 0}, {"interest_rate": -1},
])
def test_bad_input_is_rejected(logged_in, changes):
    res = logged_in.post(URL, json=with_changes(**changes))
    assert res.status_code == 422
    assert "Value error, " in res.json()["detail"][0]["msg"]  # our friendly message, not Pydantic's default


def test_falls_back_to_formula_without_model(logged_in, monkeypatch):
    monkeypatch.setattr(routes.loans, "loan_model", None)
    data = logged_in.post(URL, json=GOOD).json()
    assert data["source"] == "formula"
    assert data["predicted_max_loan"] == data["formula_max_loan"]


def test_missing_model_file_gives_none_not_crash(tmp_path):
    assert routes.loans.load_model(tmp_path / "nope.pkl") is None


def test_credit_score_range_matches_training_data():
    pd = pytest.importorskip("pandas")
    csv = Path(routes.loans.__file__).resolve().parent.parent / "DATA" / "synthetic_loan_data.csv"
    if not csv.exists():
        pytest.skip("training CSV not present")
    scores = pd.read_csv(csv, usecols=["credit_score"])["credit_score"]
    assert (scores.min(), scores.max()) == (CREDIT_SCORE_MIN, CREDIT_SCORE_MAX)


def test_predict_needs_login(client):
    assert client.post(URL, json=GOOD).status_code == 401


# ===== MORE CHECKS (full test pass) =====
@pytest.mark.parametrize("changes", [{"monthly_income": 1e20}, {"credit_score": "abc"}, {"age": "old"},
                                     {"monthly_income": None}, {"years": 1e20}])
def test_huge_or_text_input_is_rejected(logged_in, changes):  # 1e20 / text / null -> 422, never 500
    assert logged_in.post(URL, json=with_changes(**changes)).status_code == 422


def test_debt_to_income_ratio_is_repayments_over_income(logged_in):  # 9000 / 45000 = 0.2
    data = logged_in.post(URL, json=with_changes(monthly_income=45000, existing_debt_payment=9000)).json()
    assert data["debt_to_income_ratio"] == 0.2


def test_model_gets_its_ratio_as_expenses_plus_debt_over_income(monkeypatch):  # model feature = (30000+6000)/60000
    seen = []

    class FakeModel:
        def predict(self, frame):
            seen.append(list(frame.columns) + list(frame.iloc[0]))
            return [123.0]

    monkeypatch.setattr(routes.loans, "loan_model", FakeModel())
    assert routes.loans.predict_with_model(routes.loans.LoanPredictForm(**GOOD)) == 123.0
    assert seen[0][:6] == routes.loans.FEATURES and seen[0][-1] == 0.6


def test_negative_model_answer_is_clamped_to_zero(logged_in, monkeypatch):  # model says -500 -> 0
    class NegativeModel:
        def predict(self, frame):
            return [-500.0]

    monkeypatch.setattr(routes.loans, "loan_model", NegativeModel())
    data = logged_in.post(URL, json=GOOD).json()
    assert data["predicted_max_loan"] == 0 and data["source"] == "ai"


def test_broken_model_falls_back_to_formula(logged_in, monkeypatch):  # model raises -> formula answer, not 500
    class BrokenModel:
        def predict(self, frame):
            raise ValueError("broken")

    monkeypatch.setattr(routes.loans, "loan_model", BrokenModel())
    data = logged_in.post(URL, json=GOOD).json()
    assert data["source"] == "formula" and data["predicted_max_loan"] == data["formula_max_loan"]


def test_debt_above_40_percent_gives_zero_formula_loan(logged_in):  # rule payment can't go negative
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=50000)).json()
    assert data["formula_monthly_payment"] == 0 and data["formula_max_loan"] == 0


def test_zero_interest_rule_amount(logged_in):  # 0% -> payment x months
    data = logged_in.post(URL, json=with_changes(interest_rate=0, years=1)).json()
    assert data["formula_max_loan"] == 18000 * 12
