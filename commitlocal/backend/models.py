# models.py — the shape of the data the frontend sends us. FastAPI rejects anything that doesn't fit.
import datetime

from pydantic import BaseModel, EmailStr, Field

MAX_AMOUNT = 10_000_000  # no single amount above Rs 1 crore


class RegisterForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(max_length=200)
    confirm_password: str = Field(max_length=200)


class LoginForm(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class EmailForm(BaseModel):
    email: EmailStr


class CodeForm(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")  # exactly 6 digits


class ExpenseForm(BaseModel):
    amount: float = Field(gt=0, le=MAX_AMOUNT)       # no zero, negative or huge amounts
    category: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=100)     # the description
    date: datetime.date | None = None                 # empty = today


class BudgetForm(BaseModel):
    monthly_limit: float = Field(gt=0, le=MAX_AMOUNT)
