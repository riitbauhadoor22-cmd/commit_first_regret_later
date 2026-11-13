# test_loans.py — POST /api/loans/predict (real-data risk model + 40% rule) and train_loan_risk_model.py.
import json

import pytest

import routes.loans

URL = "/api/loans/predict"
GOOD = {"monthly_income": 60000, "monthly_expenses": 30000, "existing_debt_payment": 6000,
        "interest_rate": 10, "years": 5}
FIXTURE = routes.loans.Path(__file__).resolve().parents[1] / "fixtures" / "lending_club_sample.csv"  # FAKE data
FAKE_CARD = {"base_default_rate": 0.2, "rows_used": 1000, "date_from": "2007-06", "date_to": "2015-12",
             "dataset": "test"}


# ===== HELPERS =====
def with_changes(**changes):
    return {**GOOD, **changes}


class FakeModel:
    """Risk = a fixed number, or a function of the feature rows."""

    def __init__(self, risk):
        self.risk = risk

    def predict_proba(self, frame):
        risks = [self.risk(row) if callable(self.risk) else self.risk for _, row in frame.iterrows()]
        import numpy as np
        return np.array([[1 - r, r] for r in risks])


@pytest.fixture
def fake_model(monkeypatch):
    """Use a fake model + card: call it with a risk (number or function of the feature row)."""
    def use(risk):
        monkeypatch.setattr(routes.loans, "loan_model", FakeModel(risk))
        monkeypatch.setattr(routes.loans, "model_card", FAKE_CARD)
    return use


# ===== TESTS: API =====
def test_valid_input_returns_numbers(logged_in):
    res = logged_in.post(URL, json=GOOD)
    assert res.status_code == 200
    data = res.json()
    assert data["predicted_max_loan"] >= 0
    assert data["debt_to_income_ratio"] == 0.1  # 6000 / 60000, as a fraction
    assert data["verdict"] == "Good to borrow"
    # 40% rule: 24000 − 6000 = Rs 18,000 a month, 60 months at 10% a year
    assert data["formula_monthly_payment"] == 18000
    assert data["formula_max_loan"] == pytest.approx(847 * 1000, rel=0.01)
    if routes.loans.loan_model is not None and routes.loans.model_card is not None:
        assert data["source"] == "ai" and data["model_info"]["rows"] > 0
        assert data["risk_level"] in ("low", "medium", "high")


@pytest.mark.parametrize("ratio_debt, verdict", [(18000, "Borrow carefully"), (24000, "Borrow carefully"),
                                                  (30000, "Not recommended right now")])
def test_verdicts(logged_in, ratio_debt, verdict):
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=ratio_debt)).json()
    assert data["verdict"] == verdict
    assert data["predicted_max_loan"] >= 0 and data["formula_max_loan"] >= 0  # never negative


@pytest.mark.parametrize("changes", [
    {"monthly_income": 0}, {"monthly_income": -5}, {"monthly_expenses": -1}, {"existing_debt_payment": -1},
    {"monthly_income": 10 ** 12}, {"years": 0}, {"interest_rate": -1},
])
def test_bad_input_is_rejected(logged_in, changes):
    res = logged_in.post(URL, json=with_changes(**changes))
    assert res.status_code == 422
    assert "Value error, " in res.json()["detail"][0]["msg"]  # our friendly message, not Pydantic's default


@pytest.mark.parametrize("changes", [{"monthly_income": 1e20}, {"missed_payment": "maybe"},
                                     {"monthly_income": None}, {"years": 1e20}])
def test_huge_or_text_input_is_rejected(logged_in, changes):  # 1e20 / text / null -> 422, never 500
    assert logged_in.post(URL, json=with_changes(**changes)).status_code == 422


def test_predict_needs_login(client):
    assert client.post(URL, json=GOOD).status_code == 401


def test_debt_to_income_ratio_is_repayments_over_income(logged_in):  # 9000 / 45000 = 0.2
    data = logged_in.post(URL, json=with_changes(monthly_income=45000, existing_debt_payment=9000)).json()
    assert data["debt_to_income_ratio"] == 0.2


def test_debt_above_40_percent_gives_zero_formula_loan(logged_in):  # rule payment can't go negative
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=50000)).json()
    assert data["formula_monthly_payment"] == 0 and data["formula_max_loan"] == 0
    assert data["predicted_max_loan"] == 0  # final answer is never above the rule


def test_zero_interest_rule_amount(logged_in):  # 0% -> payment x months
    data = logged_in.post(URL, json=with_changes(interest_rate=0, years=1)).json()
    assert data["formula_max_loan"] == 18000 * 12


# ===== TESTS: FALLBACK =====
def test_falls_back_to_rule_without_model(logged_in, monkeypatch):
    monkeypatch.setattr(routes.loans, "loan_model", None)
    data = logged_in.post(URL, json=GOOD).json()
    assert data["source"] == "formula" and data["ai_max_loan"] is None and data["risk_level"] is None
    assert data["predicted_max_loan"] == data["formula_max_loan"]


def test_falls_back_without_model_card(logged_in, monkeypatch, fake_model):
    fake_model(0.01)
    monkeypatch.setattr(routes.loans, "model_card", None)
    assert logged_in.post(URL, json=GOOD).json()["source"] == "formula"


def test_missing_files_give_none_not_crash(tmp_path):
    assert routes.loans.load_model(tmp_path / "nope.pkl") is None
    assert routes.loans.load_card(tmp_path / "nope.json") is None


def test_broken_model_falls_back_to_rule(logged_in, fake_model):  # model raises -> rule answer, not 500
    fake_model(lambda row: 1 / 0)
    data = logged_in.post(URL, json=GOOD).json()
    assert data["source"] == "formula" and data["predicted_max_loan"] == data["formula_max_loan"]


def test_app_does_not_load_the_synthetic_model():
    assert routes.loans.MODEL_PATH.name == "loan_risk_model.pkl"


# ===== TESTS: AI ESTIMATE =====
@pytest.mark.parametrize("risk", [0.0, 0.1, 0.19, 0.5])
def test_final_answer_never_above_rule(logged_in, fake_model, risk):
    fake_model(risk)
    data = logged_in.post(URL, json=GOOD).json()
    assert data["predicted_max_loan"] <= data["formula_max_loan"]
    assert data["predicted_max_loan"] == min(data["ai_max_loan"], data["formula_max_loan"])


def test_low_risk_everywhere_rule_is_the_limit(logged_in, fake_model):
    fake_model(0.01)
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=18000)).json()  # rule allows only 10%
    assert data["limited_by"] == "rule" and data["risk_level"] == "low" and data["source"] == "ai"
    assert data["model_info"]["rows"] == 1000


def test_high_risk_everywhere_gives_zero(logged_in, fake_model):
    fake_model(0.5)  # above the 0.2 base rate even for Rs 0
    data = logged_in.post(URL, json=GOOD).json()
    assert data["ai_max_loan"] == 0 and data["predicted_max_loan"] == 0
    assert data["limited_by"] == "ai" and data["risk_level"] == "high"


def test_ai_estimate_is_last_amount_at_or_below_base_rate(logged_in, fake_model):
    fake_model(lambda row: 0.1 if row["loan_to_income"] * 60000 * 12 <= 100000 else 0.3)  # risky above Rs 100,000
    data = logged_in.post(URL, json=GOOD).json()
    assert data["ai_max_loan"] == 100000 and data["limited_by"] == "ai"


def test_model_features_match_lending_club_meaning(fake_model):
    seen = []
    fake_model(lambda row: seen.append(dict(row)) or 0.1)
    form = routes.loans.LoanPredictForm(**with_changes(missed_payment=True, years=1))
    routes.loans.predict_risks(form, [120000])
    row = seen[0]
    assert list(row) == routes.loans.FEATURES
    assert row["dti"] == 0.1  # existing repayments / income, NOT counting the new loan
    assert row["loan_to_income"] == pytest.approx(120000 / 720000)
    assert row["payment_to_income"] == pytest.approx(routes.loans.monthly_payment(120000, 10, 1) / 60000)
    assert row["term_months"] == 36 and row["missed_payment"] == 1  # term clipped to Lending Club's 36–60


# ===== TESTS: REAL MODEL (skipped if not trained) =====
def test_real_model_more_payment_burden_means_more_risk():
    model = routes.loans.load_model(routes.loans.MODEL_PATH)
    if model is None:
        pytest.skip("loan_risk_model.pkl not trained")
    import pandas as pd
    rows = [[burden, 0.1, burden * 2, 12.0, 36, 0] for burden in (0.03, 0.12, 0.25)]
    risks = model.predict_proba(pd.DataFrame(rows, columns=routes.loans.FEATURES))[:, 1]
    assert risks[0] < risks[1] < risks[2]


# ===== TESTS: TRAINING SCRIPT (on the tiny FAKE fixture) =====
def test_training_script_runs_on_fixture(tmp_path):
    pytest.importorskip("sklearn")
    import train_loan_risk_model
    card = train_loan_risk_model.main(["--input", str(FIXTURE), "--out-dir", str(tmp_path)])
    assert (tmp_path / "loan_risk_model.pkl").exists()
    saved = json.loads((tmp_path / "loan_risk_model_card.json").read_text(encoding="utf-8"))
    assert saved == card
    assert card["rows_read"] == 165 and card["rows_used"] == 161  # 4 bad rows dropped (status, year, income, dti)
    assert card["date_to"] <= "2015-12" and card["features"] == routes.loans.FEATURES
    assert 0 < card["base_default_rate"] < 1 and 0 <= card["test_roc_auc"] <= 1
    assert [b["payment_to_income"] for b in card["payment_to_income_bands"]] == ["<10%", "10-20%", "20-30%", ">30%"]
    assert routes.loans.load_model(tmp_path / "loan_risk_model.pkl") is not None


def test_ai_search_stops_at_30_percent_of_income(logged_in, fake_model):  # real data has almost no bigger loans
    fake_model(0.01)
    data = logged_in.post(URL, json=with_changes(existing_debt_payment=0)).json()
    assert routes.loans.monthly_payment(data["ai_max_loan"], 10, 5) <= 60000 * 0.30
    assert routes.loans.monthly_payment(data["ai_max_loan"] + 5000, 10, 5) > 60000 * 0.30
