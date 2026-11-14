# routes/my_loans.py — /api/my-loans: loans the user CHOSE to save from the Loans tab (all optional).
# list (+ total monthly repayments), add, edit, delete. No loans saved = "no loan info", never "Rs 0 of loans".
import uuid

from fastapi import APIRouter, Depends

from database import find_user_row, get_user_rows, open_db
from errors import AppError
from models import MyLoan, MyLoanForm
from money import get_total, to_cents, to_money
from routes.auth import require_user

router = APIRouter(prefix="/api/my-loans")


# ===== HELPERS =====
def find_loan(db, loan_id, user_id):
    row = find_user_row(db, MyLoan, loan_id, user_id)
    if row is None:
        raise AppError(404, "LOAN_NOT_FOUND", "Loan not found.")
    return row


def fill_loan(row, form):
    row.name = form.name.strip()
    row.balance_cents = to_cents(form.balance)
    row.annual_rate = round(form.annual_rate, 2)
    row.monthly_payment_cents = to_cents(form.monthly_payment)
    row.start_date = form.start_date


def build_loans_info(db, user_id):
    loans = get_user_rows(db, MyLoan, user_id)
    payments = [{"amount": loan["monthly_payment"]} for loan in loans]
    return {"loans": loans, "total_monthly_payment": to_money(get_total(payments))}


# ===== ROUTES =====
@router.get("")
def list_loans(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return build_loans_info(db, user_id)


@router.post("", status_code=201)
def add_loan(form: MyLoanForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        row = MyLoan(user_id=user_id)
        fill_loan(row, form)
        db.add(row)
        db.flush()
        return build_loans_info(db, user_id)


@router.put("/{loan_id}")
def edit_loan(loan_id: uuid.UUID, form: MyLoanForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        fill_loan(find_loan(db, loan_id, user_id), form)
        db.flush()
        return build_loans_info(db, user_id)


@router.delete("/{loan_id}")
def delete_loan(loan_id: uuid.UUID, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        db.delete(find_loan(db, loan_id, user_id))
        db.flush()
        return build_loans_info(db, user_id)
