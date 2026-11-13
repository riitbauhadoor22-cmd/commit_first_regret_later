# errors.py — error replies with a CODE the frontend can translate (frontend/lang/*.json, keys "error.<CODE>").
# Every error reply looks like {"detail": <English message or Pydantic list>, "code": "INVALID_AMOUNT", "params": {...}}.
# "detail" stays as before, so older code (and tests) that read it keep working. The backend never translates.
import math

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# ===== OUR OWN ERRORS =====
class AppError(HTTPException):
    """Like HTTPException, plus a short code (e.g. "WRONG_CODE") and optional values for the text (e.g. {"left": 2})."""

    def __init__(self, status_code, code, message, params=None):
        super().__init__(status_code, message)
        self.code = code
        self.params = params or {}


# ===== FORM (422) ERRORS: field name → code =====
FIELD_CODES = {
    "amount": "INVALID_AMOUNT", "monthly_limit": "INVALID_AMOUNT", "target_amount": "INVALID_AMOUNT",
    "bank_balance": "INVALID_AMOUNT", "monthly_target": "INVALID_AMOUNT",
    "monthly_expenses": "INVALID_EXPENSES", "existing_debt_payment": "INVALID_EXPENSES",
    "monthly_income": "INVALID_INCOME", "credit_score": "INVALID_CREDIT_SCORE", "age": "INVALID_AGE",
    "interest_rate": "INVALID_RATE", "years": "INVALID_YEARS",
    "category": "INVALID_CATEGORY", "type": "INVALID_INCOME_TYPE", "frequency": "INVALID_INPUT",
    "email": "INVALID_EMAIL", "code": "INVALID_CODE_FORMAT", "date": "INVALID_DATE", "deadline": "INVALID_DATE",
    "name": "INVALID_NAME", "full_name": "INVALID_NAME", "note": "INVALID_NOTE",
    "language": "INVALID_LANGUAGE",
}


def code_for_validation(errors):
    """The code for the first problem in a Pydantic error list."""
    if not errors:
        return "INVALID_INPUT"
    first = errors[0]
    field = first.get("loc", [""])[-1]  # e.g. ("body", "amount") → "amount"
    if first.get("type") == "missing" and field not in FIELD_CODES:
        return "MISSING_FIELD"
    return FIELD_CODES.get(field, "INVALID_INPUT")


# ===== HANDLERS (connected in main.py) =====
async def app_error_handler(request: Request, error: AppError):
    return JSONResponse(status_code=error.status_code, headers=error.headers,
                        content={"detail": error.detail, "code": error.code, "params": error.params})


def make_json_safe(value):
    """Infinity / NaN can't go in a JSON reply (it crashed with a 500), so they become text."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    return value


async def validation_error_handler(request: Request, error: RequestValidationError):
    errors = error.errors()
    return JSONResponse(status_code=422, content={"detail": make_json_safe(jsonable_encoder(errors)),
                                                  "code": code_for_validation(errors), "params": {}})


def add_error_handlers(app):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
