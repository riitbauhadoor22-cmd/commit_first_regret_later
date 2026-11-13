# models.py — the shape of the data the frontend sends us. FastAPI rejects anything that doesn't fit.
from pydantic import BaseModel, EmailStr, Field


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
