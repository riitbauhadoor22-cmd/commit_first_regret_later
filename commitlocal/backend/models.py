# models.py — the shape of the data the frontend sends us. FastAPI rejects anything that doesn't fit.
import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from categories import CATEGORIES, INCOME_TYPES

MAX_AMOUNT = 10_000_000


# ===== LOGIN FORMS =====

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


# ===== MONEY FORMS =====
class IncomeForm(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str
    amount: float = Field(gt=0, le=MAX_AMOUNT)
    frequency: Literal["monthly", "weekly", "one-off"]
    date: datetime.date

    @field_validator("type")
    @classmethod
    def check_type(cls, value):
        if value not in INCOME_TYPES:
            raise ValueError("Pick one of: " + ", ".join(INCOME_TYPES))
        return value


class ExpenseForm(BaseModel):
    amount: float = Field(gt=0, le=MAX_AMOUNT)
    category: str
    kind: Optional[Literal["need", "want"]] = None   # empty = use the category's default
    note: str = Field(default="", max_length=100)
    date: Optional[datetime.date] = None                     # empty = today
    is_fixed: bool = False
    source: Literal["typed", "voice", "quick"] = "typed"

    @field_validator("category")
    @classmethod
    def check_category(cls, value):
        if value not in CATEGORIES:
            raise ValueError("Pick one of: " + ", ".join(CATEGORIES))
        return value


class QuickAddForm(BaseModel):
    note: str = Field(default="", max_length=100)
    amount: float = Field(gt=0, le=MAX_AMOUNT)


class BudgetForm(BaseModel):
    category: str
    monthly_limit: Optional[float] = Field(default=None, gt=0, le=MAX_AMOUNT)  # empty = remove the budget

    @field_validator("category")
    @classmethod
    def check_category(cls, value):
        if value not in CATEGORIES:
            raise ValueError("Pick one of: " + ", ".join(CATEGORIES))
        return value


class SavingsForm(BaseModel):
    bank_balance: float = Field(ge=0, le=MAX_AMOUNT)
    monthly_target: Optional[float] = Field(default=None, ge=0, le=MAX_AMOUNT)  # empty = 20% of regular income


class GoalForm(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    target_amount: float = Field(gt=0, le=MAX_AMOUNT)
    deadline: datetime.date
    priority: int = Field(default=2, ge=1, le=3)  # 1 High, 2 Medium, 3 Low


class AddMoneyForm(BaseModel):
    amount: float = Field(gt=0, le=MAX_AMOUNT)
