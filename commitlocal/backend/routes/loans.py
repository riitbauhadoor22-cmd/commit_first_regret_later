# routes/loans.py — POST /api/loans/predict: "Can I afford a loan?" on the Loans tab.
# Uses a risk model trained on REAL loan outcomes (AI_model/loan_risk_model.pkl, made by train_loan_risk_model.py,
# loaded ONCE when the app starts) + its model card (base default rate, rows, dates). It tries loan amounts in
# Rs 5,000 steps and keeps the biggest one whose predicted risk of not repaying is at or below the average.
# The final answer is the lower of that and the 40% debt-to-income rule. No model → the 40% rule only.
# NOTE: the old synthetic model (AI_model/loan_amount_model.pkl, DATA/synthetic_loan_data.csv,
# train_loan_model.py) is left on disk but is NOT used anymore.
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends

from models import LoanPredictForm
from routes.auth import require_user

router = APIRouter(prefix="/api/loans")
log = logging.getLogger(__name__)

# ===== SETTINGS =====
MODEL_DIR = Path(__file__).resolve().parent.parent / "AI_model"
MODEL_PATH = MODEL_DIR / "loan_risk_model.pkl"
CARD_PATH = MODEL_DIR / "loan_risk_model_card.json"
# The model expects exactly these columns, in this order (see train_loan_risk_model.py)
FEATURES = ["payment_to_income", "dti", "loan_to_income", "int_rate", "term_months", "missed_payment"]
MAX_DEBT_TO_INCOME = 0.4  # same rule as frontend/loan-calc.js: all loan repayments ≤ 40% of income
SEARCH_STEP = 5000              # try Rs 0, 5,000, 10,000, ...
SEARCH_MAX = 10_000_000         # ... up to Rs 1 crore
SEARCH_MAX_INCOME_YEARS = 5     # ... or 5 years of income, whichever is lower (training data drops bigger loans)
# Real data has almost no loans costing over 30% of monthly income (20 of 825k), so the model can't judge them:
# the AI search stops there.
MAX_PAYMENT_TO_INCOME = 0.30
TRAINED_TERMS = (36, 60)        # Lending Club loans are 3 or 5 years: other terms are clipped to this range
RISK_LOW_BELOW = 0.8            # risk < 0.8 × base rate → "low"
RISK_HIGH_ABOVE = 1.2           # risk > 1.2 × base rate → "high"; in between → "medium"


# ===== LOAD THE MODEL + CARD (once, at start-up) =====
def load_model(path):
    """The trained model, or None (with a clear log message) if the file is missing or broken."""
    try:
        import joblib  # imported here so a missing package also falls back instead of crashing
        model = joblib.load(path)
        log.info("Loan risk model loaded from %s", path)
        return model
    except Exception as error:  # missing file, missing package, version problem...
        log.error("Could not load the loan risk model (%s): %s. Using the 40%% rule only.", path, error)
        return None


def load_card(path):
    """The model card (dict) or None. Without its base default rate the model can't be used."""
    try:
        card = json.loads(Path(path).read_text(encoding="utf-8"))
        float(card["base_default_rate"])  # must be there
        return card
    except Exception as error:
        log.error("Could not read the loan model card (%s): %s. Using the 40%% rule only.", path, error)
        return None


loan_model = load_model(MODEL_PATH)
model_card = load_card(CARD_PATH)


# ===== HELPERS =====
def max_loan_for_payment(payment, annual_percent, years):
    """Biggest loan a fixed monthly payment pays off in `years` (present value, monthly compounding)."""
    months = years * 12
    rate = annual_percent / 100 / 12
    if payment <= 0:
        return 0.0
    if rate == 0:
        return payment * months
    return payment * (1 - (1 + rate) ** -months) / rate


def monthly_payment(amount, annual_percent, years):
    """Amortised monthly installment for a loan (same maths as LoanCalc.repaymentFor in the frontend)."""
    months = years * 12
    rate = annual_percent / 100 / 12
    if rate == 0:
        return amount / months
    return amount * rate / (1 - (1 + rate) ** -months)


def get_verdict(ratio):
    """Existing repayments as a fraction of income → plain-language verdict."""
    if ratio < 0.30:
        return "Good to borrow"
    if ratio <= MAX_DEBT_TO_INCOME:
        return "Borrow carefully"
    return "Not recommended right now"


def risk_level(risk, base_rate):
    if risk < base_rate * RISK_LOW_BELOW:
        return "low"
    if risk <= base_rate * RISK_HIGH_ABOVE:
        return "medium"
    return "high"


def predict_risks(form, amounts):
    """Predicted chance of not repaying for each loan amount (list of fractions). Raises if the model fails."""
    import pandas as pd
    income = form.monthly_income
    term = min(max(form.years * 12, TRAINED_TERMS[0]), TRAINED_TERMS[1])
    rows = [[monthly_payment(amount, form.interest_rate, form.years) / income,
             form.existing_debt_payment / income,  # like LC's dti: existing debt, not counting the new loan
             amount / (income * 12), form.interest_rate, term, 1 if form.missed_payment else 0]
            for amount in amounts]
    return [float(p) for p in loan_model.predict_proba(pd.DataFrame(rows, columns=FEATURES))[:, 1]]


def search_amounts(monthly_income):
    cap = min(SEARCH_MAX, monthly_income * 12 * SEARCH_MAX_INCOME_YEARS)
    return [step * SEARCH_STEP for step in range(int(cap // SEARCH_STEP) + 1)]


def model_info(card):
    return {"rows": card.get("rows_used"), "date_from": card.get("date_from"),
            "date_to": card.get("date_to"), "dataset": card.get("dataset")}


# ===== ROUTES =====
@router.post("/predict")
def predict_max_loan(form: LoanPredictForm, user_id: uuid.UUID = Depends(require_user)):
    ratio = form.existing_debt_payment / form.monthly_income  # fraction: 0.25 = 25% of income

    # Standard rule: (40% of income − existing repayments) as the monthly payment, turned into a loan
    # amount at the interest rate and term sent by the frontend (default 10% a year for 5 years).
    formula_payment = max(form.monthly_income * MAX_DEBT_TO_INCOME - form.existing_debt_payment, 0.0)
    formula_max_loan = max_loan_for_payment(formula_payment, form.interest_rate, form.years)

    answer = {"predicted_max_loan": round(formula_max_loan, 2), "ai_max_loan": None, "limited_by": "rule",
              "predicted_risk": None, "risk_level": None, "base_default_rate": None, "model_info": None,
              "source": "formula"}  # "formula" = model unavailable, only the 40% rule was used
    if loan_model is not None and model_card is not None:
        try:
            base_rate = float(model_card["base_default_rate"])
            amounts = search_amounts(form.monthly_income)
            risks = predict_risks(form, amounts)
            ai_max = 0.0
            for amount, risk in zip(amounts, risks):  # stop at the first amount that is riskier than average
                too_costly = monthly_payment(amount, form.interest_rate, form.years) > form.monthly_income * MAX_PAYMENT_TO_INCOME
                if risk > base_rate or too_costly:
                    break
                ai_max = float(amount)
            final = min(ai_max, formula_max_loan)
            shown = final if final > 0 else SEARCH_STEP  # nothing safe → show the risk of the smallest loan
            risk = predict_risks(form, [shown])[0]
            answer = {"predicted_max_loan": round(final, 2), "ai_max_loan": round(ai_max, 2),
                      "limited_by": "ai" if ai_max < formula_max_loan else "rule",
                      "predicted_risk": round(risk, 4), "risk_level": risk_level(risk, base_rate),
                      "base_default_rate": base_rate, "model_info": model_info(model_card),
                      "max_payment_to_income": MAX_PAYMENT_TO_INCOME, "source": "ai"}
        except Exception as error:
            log.error("Loan risk model failed: %s. Using the 40%% rule instead.", error)

    return {**answer,
            "formula_max_loan": round(formula_max_loan, 2),
            "formula_monthly_payment": round(formula_payment, 2),
            "debt_to_income_ratio": round(ratio, 4),
            "verdict": get_verdict(ratio)}
