# routes/loans.py — POST /api/loans/predict: "How much can I borrow?" on the Loans tab.
# Uses the trained RandomForest model (AI_model/loan_amount_model.pkl, loaded ONCE when the app starts)
# and also the simple 40% debt-to-income rule. If the model can't be loaded, the rule is used instead.
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends

from models import LoanPredictForm
from routes.auth import require_user

router = APIRouter(prefix="/api/loans")
log = logging.getLogger(__name__)

# ===== SETTINGS =====
MODEL_PATH = Path(__file__).resolve().parent.parent / "AI_model" / "loan_amount_model.pkl"
# The model expects exactly these columns, in this order (see train_loan_model.py)
FEATURES = ["monthly_income", "monthly_expenses", "existing_debt_payment", "credit_score", "age", "debt_to_income_ratio"]
MAX_DEBT_TO_INCOME = 0.4  # same rule as frontend/loan-calc.js: all loan repayments ≤ 40% of income


# ===== LOAD THE MODEL (once, at start-up) =====
def load_model(path):
    """The trained model, or None (with a clear log message) if the file is missing or broken."""
    try:
        import joblib  # imported here so a missing package also falls back instead of crashing
        model = joblib.load(path)
        log.info("Loan model loaded from %s", path)
        return model
    except Exception as error:  # missing file, missing package, version problem...
        log.error("Could not load the loan model (%s): %s. Using the 40%% debt-to-income rule instead.", path, error)
        return None


loan_model = load_model(MODEL_PATH)


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


def get_verdict(ratio):
    """Existing repayments as a fraction of income → plain-language verdict."""
    if ratio < 0.30:
        return "Good to borrow"
    if ratio <= MAX_DEBT_TO_INCOME:
        return "Borrow carefully"
    return "Not recommended right now"


def predict_with_model(form):
    """Model prediction in rupees (never negative). Raises if the model fails."""
    import pandas as pd
    # The training CSV's debt_to_income_ratio is (expenses + existing debt) / income, as a fraction (e.g. 0.646),
    # rounded to 3 decimals — so we build it the same way for the model.
    model_ratio = round((form.monthly_expenses + form.existing_debt_payment) / form.monthly_income, 3)
    row = [[form.monthly_income, form.monthly_expenses, form.existing_debt_payment,
            form.credit_score, form.age, model_ratio]]
    prediction = float(loan_model.predict(pd.DataFrame(row, columns=FEATURES))[0])
    return max(prediction, 0.0)


# ===== ROUTES =====
@router.post("/predict")
def predict_max_loan(form: LoanPredictForm, user_id: uuid.UUID = Depends(require_user)):
    ratio = form.existing_debt_payment / form.monthly_income  # fraction: 0.25 = 25% of income

    # Standard rule: (40% of income − existing repayments) as the monthly payment, turned into a loan
    # amount at the interest rate and term sent by the frontend (default 10% a year for 5 years).
    formula_payment = max(form.monthly_income * MAX_DEBT_TO_INCOME - form.existing_debt_payment, 0.0)
    formula_max_loan = max_loan_for_payment(formula_payment, form.interest_rate, form.years)

    source = "formula"
    predicted = formula_max_loan
    if loan_model is not None:
        try:
            predicted = predict_with_model(form)
            source = "ai"
        except Exception as error:
            log.error("Loan model prediction failed: %s. Using the 40%% rule instead.", error)

    return {
        "predicted_max_loan": round(predicted, 2),
        "formula_max_loan": round(formula_max_loan, 2),
        "formula_monthly_payment": round(formula_payment, 2),
        "debt_to_income_ratio": round(ratio, 4),
        "verdict": get_verdict(ratio),
        "source": source,  # "ai" = model answer, "formula" = model unavailable, the 40% rule was used
    }
