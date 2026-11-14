# routes/profile.py — the Profile tab's "My account" part. Every route works on the LOGGED-IN user only
# (the id comes from the session cookie via require_user, never from the browser).
#   GET /api/profile             → {full_name, username, email, phone, occupation}  (NEVER the password or its hash)
#   PUT /api/profile/name        → {full_name}                     same rules as registration
#   PUT /api/profile/username    → {username}                      3–30 letters/numbers/. _ -, lowercase, unique
#   PUT /api/profile/email       → {email, current_password}       lowercase, unique, needs the current password;
#                                  empty = remove (only while a phone number is left)
#   PUT /api/profile/phone       → {phone, current_password}       Mauritius number (+230…), unique, needs the password;
#                                  empty = remove (only while an email is left). Both can't be removed.
#   PUT /api/profile/occupation  → {occupation}                    free text up to 60 characters or empty (= remove)
#   PUT /api/profile/password    → {current_password, new_password, confirm_password}  same rules as registration;
#                                  other logged-in devices are logged out, this one stays logged in
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select

from database import open_db
from errors import AppError
from models import (ChangeEmailForm, ChangePasswordForm, LoginSession, NameForm, OccupationForm, PhoneForm, Profile,
                    User, UsernameForm)
from routes.auth import COOKIE_NAME, find_user, find_user_by_phone, find_user_by_username, require_user
from security import get_password_problems, hash_password, hash_text, password_matches

router = APIRouter(prefix="/api/profile")


# ===== HELPERS =====
def load_account(db, user_id):
    """(user row, profile row) of the logged-in user. Old accounts without a profile row get an empty one."""
    user = db.get(User, user_id)
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        profile = Profile(user_id=user_id, full_name="")
        db.add(profile)
    return user, profile


def profile_reply(user, profile):
    """What the Profile tab shows. The password and its hash are never part of it."""
    return {"full_name": profile.full_name or "", "username": user.username, "email": user.email,
            "phone": profile.phone, "occupation": profile.occupation}


def keep_one_contact(email, phone):
    """An account always keeps an email or a phone number (they are how the user logs in)."""
    if not email and not phone:
        raise AppError(400, "NEED_EMAIL_OR_PHONE", "Keep an email or a phone number: you need one to log in.")


def require_current_password(user, password):
    # 400 (not 401): a 401 would make the app think the session ended and go to the login page
    if not password_matches(password, user.password_hash):
        raise AppError(400, "WRONG_PASSWORD", "Your current password is not right.")


# ===== ROUTES =====
@router.get("")
def read_profile(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return profile_reply(*load_account(db, user_id))


@router.put("/name")
def change_name(form: NameForm, user_id: uuid.UUID = Depends(require_user)):
    full_name = form.full_name.strip()
    if not full_name:
        raise AppError(400, "NAME_REQUIRED", "Please enter your full name.")
    with open_db() as db:
        user, profile = load_account(db, user_id)
        profile.full_name = full_name
        return profile_reply(user, profile)


@router.put("/username")
def change_username(form: UsernameForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        user, profile = load_account(db, user_id)
        owner = find_user_by_username(db, form.username)  # form.username is trimmed + lowercase already
        if owner is not None and owner.id != user.id:
            raise AppError(409, "USERNAME_TAKEN", "This username is already taken. Please pick another one.")
        user.username = form.username
        return profile_reply(user, profile)


@router.put("/email")
def change_email(form: ChangeEmailForm, user_id: uuid.UUID = Depends(require_user)):
    """The next login code goes to the new address, so logging in again proves the user can read it."""
    email = form.email  # already lowercase (models.py), or None = remove
    with open_db() as db:
        user, profile = load_account(db, user_id)
        require_current_password(user, form.current_password)
        keep_one_contact(email, profile.phone)
        owner = find_user(db, email) if email else None
        if owner is not None and owner.id != user.id:
            raise AppError(409, "EMAIL_IN_USE", "This email is already used by another account.")
        user.email = email
        return profile_reply(user, profile)


@router.put("/phone")
def change_phone(form: PhoneForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        user, profile = load_account(db, user_id)
        require_current_password(user, form.current_password)
        keep_one_contact(user.email, form.phone)
        owner = find_user_by_phone(db, form.phone) if form.phone else None
        if owner is not None and owner.id != user.id:
            raise AppError(409, "PHONE_TAKEN", "An account with this phone number already exists.")
        profile.phone = form.phone  # "+230XXXXXXXX" or None (removed)
        return profile_reply(user, profile)


@router.put("/occupation")
def change_occupation(form: OccupationForm, user_id: uuid.UUID = Depends(require_user)):
    occupation = (form.occupation or "").strip()
    with open_db() as db:
        user, profile = load_account(db, user_id)
        profile.occupation = occupation or None  # empty = "Not added"
        return profile_reply(user, profile)


@router.put("/password")
def change_password(form: ChangePasswordForm, request: Request, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        user, profile = load_account(db, user_id)
        require_current_password(user, form.current_password)
        if form.new_password != form.confirm_password:
            raise AppError(400, "PASSWORDS_DIFFERENT", "The two passwords don't match.")
        problems = get_password_problems(form.new_password)
        if problems:
            raise AppError(400, "PASSWORD_WEAK", "Your password needs " + ", ".join(problems) + ".")
        user.password_hash = hash_password(form.new_password)
        # Log out every OTHER device (e.g. a lost phone); this browser keeps its session
        this_session = hash_text(request.cookies.get(COOKIE_NAME, ""))
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id,
                                              LoginSession.token_hash != this_session))
    return {"message": "Password changed.", "code": "PASSWORD_CHANGED"}
