# models.py — (1) the shape of the data the frontend sends us (Pydantic forms; FastAPI rejects anything
# that doesn't fit) and (2) the database tables (SQLAlchemy ORM, at the bottom of this file).
import datetime
import re
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator, model_validator

from categories import CATEGORIES, GOAL_CPI_CATEGORIES, INCOME_TYPES

MAX_AMOUNT = 10_000_000


# ===== LOGIN FORMS =====

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,30}$")  # 3–30 letters, digits, dot, underscore, hyphen
PHONE_PATTERN = re.compile(r"^(\+230)?(5\d{7}|\d{7})$")       # Mauritius: mobile 5XXXXXXX or 7-digit landline


def clean_username(value):
    """Trimmed + lowercase username, or a ValueError (shown as INVALID_USERNAME)."""
    text = str(value).strip()
    if not USERNAME_PATTERN.match(text):
        raise ValueError("A username has 3 to 30 letters, numbers, dots, underscores or hyphens.")
    return text.lower()


def clean_phone(value):
    """Mauritius phone number → "+230XXXXXXXX" (spaces / dashes removed); empty → None. Else ValueError (INVALID_PHONE)."""
    if value is None:
        return None
    text = re.sub(r"[\s-]", "", str(value))
    if text == "":
        return None
    match = PHONE_PATTERN.match(text)
    if not match:
        raise ValueError("Please enter a Mauritius phone number, e.g. +230 5123 4567.")
    return "+230" + match.group(2)


EMAIL_CHECK = TypeAdapter(EmailStr)


class CodedValueError(ValueError):
    """A form problem with its own error code (errors.py sends `code` instead of a field-name code)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def clean_email(value):
    """Optional email: empty → None, otherwise a valid email in lowercase (else ValueError = INVALID_EMAIL)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return str(EMAIL_CHECK.validate_python(str(value).strip())).lower()
    except ValueError:  # pydantic's own error → a plain message (code INVALID_EMAIL from the field name)
        raise ValueError("Please enter a valid email address.")


def clean_login_id(value):
    """Login with an email OR a phone number: "Asha@X.com" → "asha@x.com", "5123 4567" → "+23051234567"."""
    text = str(value).strip()
    if "@" in text:
        return clean_email(text)
    phone = clean_phone(text)
    if phone is None:
        raise ValueError("Please enter your email or phone number.")
    return phone


class RegisterForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    username: str = Field(max_length=60)
    email: Optional[str] = Field(default=None, max_length=254)  # email OR phone (or both) is required
    phone: Optional[str] = Field(default=None, max_length=30)   # Mauritius format, saved as +230XXXXXXXX
    password: str = Field(max_length=200)
    confirm_password: str = Field(max_length=200)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return clean_email(value)

    @model_validator(mode="after")
    def need_email_or_phone(self):
        if self.email is None and self.phone is None:
            raise CodedValueError("EMAIL_OR_PHONE_REQUIRED", "Please enter an email or a phone number (or both).")
        return self

    @field_validator("username")
    @classmethod
    def check_username(cls, value):
        return clean_username(value)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value):
        return clean_phone(value)


# "email" in the 3 login forms = the user's email OR phone number (the field keeps its old name, so old clients work)
class LoginIdForm(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def check_login_id(cls, value):
        return clean_login_id(value)


class LoginForm(LoginIdForm):
    password: str = Field(max_length=200)


class EmailForm(LoginIdForm):
    pass


class LanguageForm(BaseModel):
    language: Literal["en", "fr", "mfe"]


class CodeForm(LoginIdForm):
    code: str = Field(pattern=r"^\d{6}$")  # exactly 6 digits


# ===== LOAN FORM (Loans tab, "How much can I borrow?") =====


def check_range(value, low, high, message):
    """Friendly error when value is outside low..high (also catches NaN, which fails every comparison)."""
    if not (low <= value <= high):
        raise ValueError(message)
    return value


class LoanPredictForm(BaseModel):
    monthly_income: float
    monthly_expenses: float = 0
    existing_debt_payment: float = 0
    interest_rate: float = 10     # % a year, for the 40% rule and the risk model's installment
    years: int = 5                # loan term, same
    missed_payment: bool = False  # "Missed a payment in the last 12 months?" (risk model input)

    @field_validator("monthly_income")
    @classmethod
    def check_income(cls, value):
        if not (0 < value <= MAX_AMOUNT):
            raise ValueError("Monthly income must be more than Rs 0 (and at most Rs 1 crore).")
        return value

    @field_validator("monthly_expenses", "existing_debt_payment")
    @classmethod
    def check_not_negative(cls, value):
        return check_range(value, 0, MAX_AMOUNT, "Expenses and repayments can't be negative (or above Rs 1 crore).")

    @field_validator("interest_rate")
    @classmethod
    def check_rate(cls, value):
        return check_range(value, 0, 100, "Interest rate must be between 0% and 100% a year.")

    @field_validator("years")
    @classmethod
    def check_years(cls, value):
        return check_range(value, 1, 30, "Loan term must be between 1 and 30 years.")


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
    bank_balance: Optional[float] = Field(default=None, ge=0, le=MAX_AMOUNT)  # empty = not added (never 0 by itself)
    monthly_target: Optional[float] = Field(default=None, ge=0, le=MAX_AMOUNT)  # empty = 20% of regular income


class GoalForm(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    target_amount: float = Field(gt=0, le=MAX_AMOUNT)
    deadline: datetime.date
    priority: int = Field(default=2, ge=1, le=3)  # 1 High, 2 Medium, 3 Low
    category: Optional[str] = None  # e.g. "Phone" (see GOAL_CPI_CATEGORIES); empty = general inflation

    @field_validator("category")
    @classmethod
    def check_goal_category(cls, value):
        if value in (None, ""):
            return None
        if value not in GOAL_CPI_CATEGORIES:
            raise ValueError("Pick one of: " + ", ".join(GOAL_CPI_CATEGORIES))
        return value


class AddMoneyForm(BaseModel):
    amount: float = Field(gt=0, le=MAX_AMOUNT)


# ===== ARCADE: BUDGET CHALLENGE GAME =====
class GameStartForm(BaseModel):
    level: int = Field(ge=1, le=99)  # must also exist in game/scenarios.py (checked in the route)
    events_on: bool = True           # surprise events on/off (any level)


class GameSubmitForm(BaseModel):
    allocation: dict[str, float] = Field(max_length=20)  # {category id: rupees}
    final: bool = False                                  # False = first try (then the event shows), True = final submit

    @field_validator("allocation")
    @classmethod
    def check_amounts(cls, value):
        for amount in value.values():  # NaN / Infinity / negative / huge -> 422
            check_range(amount, 0, MAX_AMOUNT, "Amounts must be between 0 and 10,000,000.")
        return value


# ===== OPTIONAL INFORMATION: "I have none" + SAVED LOANS =====
MAX_LOAN_AMOUNT = 100_000_000  # same limit as the Loans tab (LOAN_MAX_AMOUNT in loans-tab.js)


class InfoChoiceForm(BaseModel):
    topic: Literal["income", "expenses", "loans", "savings"]
    month: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # income/expenses only; empty = this month
    none: bool  # True = "I have none" (counts as 0), False = undo (back to "not provided")


class MyLoanForm(BaseModel):
    name: str = Field(default="", max_length=60)                  # optional label, e.g. "Student loan"
    balance: float = Field(gt=0, le=MAX_LOAN_AMOUNT)               # amount still to pay back
    annual_rate: float = Field(ge=0, le=100)                       # % a year
    monthly_payment: float = Field(gt=0, le=MAX_LOAN_AMOUNT)
    start_date: Optional[datetime.date] = None


# ===== PROFILE TAB (own account only; the user always comes from the session cookie) =====
class NameForm(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)


class UsernameForm(BaseModel):
    username: str = Field(max_length=60)

    @field_validator("username")
    @classmethod
    def check_username(cls, value):
        return clean_username(value)


class ChangeEmailForm(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)  # empty = remove (only if a phone number is left)
    current_password: str = Field(max_length=200)  # needed to change the email (security)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return clean_email(value)


class OccupationForm(BaseModel):
    occupation: Optional[str] = Field(default=None, max_length=60)  # empty = remove


class PhoneForm(BaseModel):
    phone: Optional[str] = Field(default=None, max_length=30)  # empty = remove (only if an email is left)
    current_password: str = Field(max_length=200)  # the phone can be used to log in, so it needs the password

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value):
        return clean_phone(value)


class ChangePasswordForm(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)
    confirm_password: str = Field(max_length=200)


# ===== DASHBOARD =====
class WeeklyBudgetForm(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0, le=MAX_AMOUNT)  # empty = remove the weekly budget
    today: Optional[datetime.date] = None  # the phone's local date (badges count weeks from the day it was set)


# ===== FINANCIAL INSIGHTS (Groq) =====
class InsightRequestForm(BaseModel):
    month: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")  # YYYY-MM, empty = this month


# ===== DATABASE TABLES (SQLAlchemy ORM) =====
# Same code works on SQLite (development) and PostgreSQL (production).
# Rules: UUID ids, every money table has user_id -> users.id (ON DELETE CASCADE),
# money is stored as whole cents (Rs 150.50 -> 15050) and can never be negative (CHECK).
# to_dict() turns a row into the JSON the frontend expects (rupees, text dates, text ids).
import uuid  # noqa: E402

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, mapped_column  # noqa: E402

from money import to_rupees  # noqa: E402


def utc_now():
    """Current time in UTC without timezone info (stored the same way on SQLite and PostgreSQL)."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def iso(value):
    return value.isoformat() if value is not None else None


class Base(DeclarativeBase):
    # Fixed constraint names, so Alembic can change tables later (also on SQLite)
    metadata = sa.MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def id_column():
    return mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)  # random UUID, not 1, 2, 3


def user_id_column(unique=False):
    """Link to the owner. Deleting a user deletes all their rows (ON DELETE CASCADE)."""
    return mapped_column(sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True, unique=unique)


def cents_column(nullable=False, default=None):
    return mapped_column(sa.BigInteger, nullable=nullable, default=default)


def not_negative(*columns):
    """CHECK constraints so amounts can't be negative."""
    return tuple(sa.CheckConstraint(f"{c} >= 0", name=f"{c}_not_negative") for c in columns)


class User(Base):
    """Login data only."""
    __tablename__ = "users"
    id = id_column()
    email = mapped_column(sa.String(254), nullable=True, unique=True)    # always lowercase; empty = phone-only account
    username = mapped_column(sa.String(30), nullable=True, unique=True)  # always lowercase; empty for old accounts
    password_hash = mapped_column(sa.String(100), nullable=False)        # bcrypt, never the real password
    failed_attempts = mapped_column(sa.Integer, nullable=False, default=0)
    is_locked = mapped_column(sa.Boolean, nullable=False, default=False)  # locked after 3 wrong passwords
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
                      sa.CheckConstraint("username IS NULL OR username = lower(username)", name="username_lowercase"),
                      *not_negative("failed_attempts"))


class Profile(Base):
    """Personal details, kept apart from login data."""
    __tablename__ = "profiles"
    id = id_column()
    user_id = user_id_column(unique=True)  # one profile per user
    full_name = mapped_column(sa.String(100), nullable=False)
    date_of_birth = mapped_column(sa.Date, nullable=True)
    phone = mapped_column(sa.String(20), nullable=True, unique=True)  # "+230XXXXXXXX", unique; can be used to log in
    language = mapped_column(sa.String(3), nullable=True)  # en / fr / mfe, null = never chosen
    occupation = mapped_column(sa.String(60), nullable=True)  # optional (Profile tab), null = not added
    updated_at = mapped_column(sa.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    __table_args__ = (sa.CheckConstraint("language IS NULL OR language IN ('en', 'fr', 'mfe')",
                                         name="language_allowed"),)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = id_column()
    user_id = user_id_column()
    code_hash = mapped_column(sa.String(64), nullable=False)  # SHA-256 of the 6-digit code, never the code
    expires_at = mapped_column(sa.DateTime, nullable=False)
    attempts = mapped_column(sa.Integer, nullable=False, default=0)  # wrong guesses so far
    used = mapped_column(sa.Boolean, nullable=False, default=False)  # used, replaced or too many wrong guesses
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = not_negative("attempts")


class LoginSession(Base):
    """One row per logged-in browser (the cookie value is only stored as a hash)."""
    __tablename__ = "sessions"
    token_hash = mapped_column(sa.String(64), primary_key=True)
    user_id = user_id_column()
    expires_at = mapped_column(sa.DateTime, nullable=False)


class Income(Base):
    __tablename__ = "income"
    id = id_column()
    user_id = user_id_column()
    name = mapped_column(sa.String(60), nullable=False)
    source = mapped_column(sa.String(30), nullable=False)        # Salary, Allowance, Side hustle, ... (API: "type")
    amount_cents = cents_column()
    frequency = mapped_column(sa.String(10), nullable=False)     # monthly, weekly, one-off
    date = mapped_column(sa.Date, nullable=False, index=True)    # start date, or date received (one-off)
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (*not_negative("amount_cents"),
                      sa.CheckConstraint("frequency IN ('monthly', 'weekly', 'one-off')", name="frequency_valid"))

    def to_dict(self):
        return {"id": str(self.id), "user_id": str(self.user_id), "name": self.name, "type": self.source,
                "amount": to_rupees(self.amount_cents), "frequency": self.frequency, "date": iso(self.date),
                "created_at": iso(self.created_at)}


class Expense(Base):
    __tablename__ = "expenses"
    id = id_column()
    user_id = user_id_column()
    amount_cents = cents_column()
    category = mapped_column(sa.String(30), nullable=False)
    kind = mapped_column(sa.String(4), nullable=False)                       # need or want
    description = mapped_column(sa.String(100), nullable=False, default="")  # API: "note"
    date = mapped_column(sa.Date, nullable=False, index=True)                # fixed bill: first month it counts
    is_fixed = mapped_column(sa.Boolean, nullable=False, default=False)      # True = repeats every month
    source = mapped_column(sa.String(5), nullable=False, default="typed")    # typed, voice, quick
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (*not_negative("amount_cents"),
                      sa.CheckConstraint("kind IN ('need', 'want')", name="kind_valid"))

    def to_dict(self):
        return {"id": str(self.id), "user_id": str(self.user_id), "amount": to_rupees(self.amount_cents),
                "category": self.category, "kind": self.kind, "note": self.description, "date": iso(self.date),
                "is_fixed": int(self.is_fixed), "source": self.source, "created_at": iso(self.created_at)}


class Budget(Base):
    """Monthly limit for one spending category."""
    __tablename__ = "budgets"
    id = id_column()
    user_id = user_id_column()
    category = mapped_column(sa.String(30), nullable=False)
    amount_cents = cents_column()
    period = mapped_column(sa.String(10), nullable=False, default="monthly")
    start_date = mapped_column(sa.Date, nullable=False, default=datetime.date.today, index=True)
    __table_args__ = (sa.UniqueConstraint("user_id", "category", name="uq_budgets_user_category"),
                      *not_negative("amount_cents"),
                      sa.CheckConstraint("period = 'monthly'", name="period_valid"))

    def to_dict(self):
        return {"id": str(self.id), "user_id": str(self.user_id), "category": self.category,
                "monthly_limit": to_rupees(self.amount_cents)}


class SavingsSettings(Base):
    """One row per user: bank balance, monthly saving target and safety net."""
    __tablename__ = "savings_settings"
    id = id_column()
    user_id = user_id_column(unique=True)
    bank_balance_cents = cents_column(nullable=True)    # empty = not added yet (migration 0006; was 0)
    monthly_target_cents = cents_column(nullable=True)  # empty = use 20% of regular income
    safety_net_saved_cents = cents_column(default=0)
    __table_args__ = not_negative("bank_balance_cents", "monthly_target_cents", "safety_net_saved_cents")

    def to_dict(self):
        target = self.monthly_target_cents
        balance = self.bank_balance_cents
        return {"user_id": str(self.user_id), "bank_balance": to_rupees(balance) if balance is not None else None,
                "monthly_target": to_rupees(target) if target is not None else None,
                "safety_net_saved": to_rupees(self.safety_net_saved_cents)}


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    id = id_column()
    user_id = user_id_column()
    name = mapped_column(sa.String(60), nullable=False)
    target_cents = cents_column()
    saved_cents = cents_column(default=0)
    deadline = mapped_column(sa.Date, nullable=False, index=True)
    priority = mapped_column(sa.Integer, nullable=False, default=2)  # 1 High, 2 Medium, 3 Low
    category = mapped_column(sa.String(30), nullable=True)  # goal category for the inflation estimate (migration 0003)
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (*not_negative("target_cents", "saved_cents"),
                      sa.CheckConstraint("priority BETWEEN 1 AND 3", name="priority_valid"))

    def to_dict(self):
        return {"id": str(self.id), "user_id": str(self.user_id), "name": self.name,
                "target_amount": to_rupees(self.target_cents), "saved_amount": to_rupees(self.saved_cents),
                "deadline": iso(self.deadline), "priority": self.priority, "category": self.category,
                "created_at": iso(self.created_at)}


class Deposit(Base):
    """Money put into a goal (goal_id) or into the safety net (goal_id empty)."""
    __tablename__ = "deposits"
    id = id_column()
    user_id = user_id_column()
    goal_id = mapped_column(sa.Uuid, sa.ForeignKey("savings_goals.id", ondelete="CASCADE"),
                            nullable=True, index=True)
    amount_cents = cents_column()
    date = mapped_column(sa.Date, nullable=False, index=True)
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = not_negative("amount_cents")

    def to_dict(self):
        return {"id": str(self.id), "user_id": str(self.user_id),
                "goal_id": str(self.goal_id) if self.goal_id else None,
                "amount": to_rupees(self.amount_cents), "date": iso(self.date), "created_at": iso(self.created_at)}


class GameAttempt(Base):
    """One Budget Challenge game (Arcade). id = attempt_id. Never linked to the real income/expense/budget tables."""
    __tablename__ = "game_attempts"
    id = id_column()
    user_id = user_id_column()
    level = mapped_column(sa.Integer, nullable=False)
    events_on = mapped_column(sa.Boolean, nullable=False, default=True)
    event = mapped_column(sa.String(40), nullable=True)            # event id chosen at the start (empty = no event)
    stage = mapped_column(sa.String(10), nullable=False, default="start")  # start -> event (event shown) -> done
    allocation = mapped_column(sa.Text, nullable=True)             # final allocation as JSON {category: cents}
    score = mapped_column(sa.Integer, nullable=True)               # 0-100, set at the final submit
    xp = mapped_column(sa.Integer, nullable=False, default=0)
    xp_awarded = mapped_column(sa.Boolean, nullable=False, default=False)  # XP given once per attempt
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now, index=True)
    completed_at = mapped_column(sa.DateTime, nullable=True)
    __table_args__ = (*not_negative("xp"), sa.CheckConstraint("score BETWEEN 0 AND 100", name="score_valid"))

    def to_dict(self):
        return {"attempt_id": str(self.id), "level": self.level, "score": self.score, "xp": self.xp,
                "events_on": self.events_on, "created_at": iso(self.created_at), "completed_at": iso(self.completed_at)}


class SavedInsight(Base):
    """The last AI analysis of one user for one month (migration 0005). Reused until the fingerprint changes."""
    __tablename__ = "ai_insights"
    id = id_column()
    user_id = user_id_column()
    month = mapped_column(sa.String(7), nullable=False)           # YYYY-MM = the analysis period
    fingerprint = mapped_column(sa.String(64), nullable=False)    # hash of the summary that was analysed
    model = mapped_column(sa.String(80), nullable=False)          # Groq model used
    content = mapped_column(sa.Text, nullable=False)              # the checked reply, as JSON
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)  # generation time (UTC)
    __table_args__ = (sa.UniqueConstraint("user_id", "month", name="uq_ai_insights_user_month"),)


class AiRequestLog(Base):
    """One row per call we made to Groq (also failed ones): used for the daily limit and the cooldown."""
    __tablename__ = "ai_requests"
    id = id_column()
    user_id = user_id_column()
    month = mapped_column(sa.String(7), nullable=False)
    model = mapped_column(sa.String(80), nullable=False)
    outcome = mapped_column(sa.String(20), nullable=False, default="started")  # started / ok / AI_FAILED / ...
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now, index=True)


class InfoChoice(Base):
    """The user said "I have none" for a topic (migration 0006). No row = not provided yet (never read as 0).
    month = YYYY-MM for income / expenses, "" for loans / savings (whole account)."""
    __tablename__ = "info_choices"
    id = id_column()
    user_id = user_id_column()
    topic = mapped_column(sa.String(10), nullable=False)
    month = mapped_column(sa.String(7), nullable=False, default="")
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (sa.UniqueConstraint("user_id", "topic", "month", name="uq_info_choices_user_topic_month"),
                      sa.CheckConstraint("topic IN ('income', 'expenses', 'loans', 'savings')", name="topic_valid"))


class MyLoan(Base):
    """A loan the user chose to save on the Loans tab (migration 0006). Optional: no row = no loan info."""
    __tablename__ = "my_loans"
    id = id_column()
    user_id = user_id_column()
    name = mapped_column(sa.String(60), nullable=False, default="")
    balance_cents = cents_column()
    annual_rate = mapped_column(sa.Float, nullable=False)          # % a year
    monthly_payment_cents = cents_column()
    start_date = mapped_column(sa.Date, nullable=True)
    created_at = mapped_column(sa.DateTime, nullable=False, default=utc_now)
    __table_args__ = (*not_negative("balance_cents", "monthly_payment_cents"),
                      sa.CheckConstraint("annual_rate BETWEEN 0 AND 100", name="rate_valid"))

    def to_dict(self):
        return {"id": str(self.id), "name": self.name, "balance": to_rupees(self.balance_cents),
                "annual_rate": self.annual_rate, "monthly_payment": to_rupees(self.monthly_payment_cents),
                "start_date": iso(self.start_date), "created_at": iso(self.created_at)}


class WeeklyBudget(Base):
    """The user's planned spending per week (Dashboard badges, migration 0007). No row = no weekly budget."""
    __tablename__ = "weekly_budgets"
    id = id_column()
    user_id = user_id_column(unique=True)
    amount_cents = cents_column()
    set_on = mapped_column(sa.Date, nullable=False)  # weeks are counted from here (never before)
    __table_args__ = not_negative("amount_cents")

    def to_dict(self):
        return {"amount": to_rupees(self.amount_cents), "set_on": iso(self.set_on)}


class EarnedBadge(Base):
    """A Dashboard badge the user earned (migration 0007). Never deleted; one per badge code per user."""
    __tablename__ = "earned_badges"
    id = id_column()
    user_id = user_id_column()
    code = mapped_column(sa.String(30), nullable=False)        # FIRST_WEEK, BUDGET_KEEPER, CONSISTENT_PLANNER, SAVINGS_STREAK
    earned_on = mapped_column(sa.Date, nullable=False)         # the Sunday of the week that completed it
    __table_args__ = (sa.UniqueConstraint("user_id", "code", name="uq_earned_badges_user_code"),)
