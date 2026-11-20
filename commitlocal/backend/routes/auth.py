# routes/auth.py — register (name, username, email, password), log in (email + password, then a 6-digit code
# emailed by deliver_login_code / email_sender.py), unlock a locked account, log out.
# The username is never used to log in. No code is sent at registration.
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, update

import rate_limit
from config import is_production
from database import open_db
from errors import AppError
from email_sender import send_otp_email
from models import CodeForm, EmailForm, LanguageForm, LoginForm, LoginSession, OtpCode, Profile, RegisterForm, User, utc_now
from security import (get_password_problems, hash_password, hash_text, make_otp, make_session_token,
                      password_matches, same_hash, waste_password_check)

router = APIRouter(prefix="/api/auth")

MAX_PASSWORD_TRIES = 3
MAX_CODE_TRIES = 5                 # wrong guesses allowed per code
MAX_CODE_TRIES_PER_HOUR = 15       # wrong guesses allowed over all codes (new codes can't reset the count)
CODE_LIFETIME = timedelta(minutes=5)
RESEND_WAIT = timedelta(seconds=30)  # before a new code can be sent
RESEND_WINDOW = timedelta(minutes=30)  # "Resend" only works if a code was sent this recently
MAX_CODES_PER_HOUR = 5             # codes sent per account per rolling hour
SESSION_LIFETIME = timedelta(days=7)  # stay logged in for 7 days
COOKIE_NAME = "session"
# Rate limits (rate_limit.py, in memory): (most requests, per this many seconds)
LOGIN_PER_IP = (20, 15 * 60)
LOGIN_PER_ACCOUNT = (10, 15 * 60)
REGISTER_PER_IP = (10, 60 * 60)
VERIFY_PER_IP = (30, 15 * 60)
RESEND_PER_IP = (10, 15 * 60)        # resend-code and send-login-code
WRONG_CODES_PER_IP = (10, 60 * 60)   # below MAX_CODE_TRIES_PER_HOUR: one attacker can't use up a victim's hourly tries
CODES_PER_DAY_PER_IP = (20, 24 * 60 * 60)
CODES_PER_DAY_PER_ACCOUNT = 10       # counted in the database (otp_codes), so a restart doesn't reset it
LOCKED_MESSAGE = "Your account is locked after 3 wrong passwords. Tap 'Send me a login code'."


# ===== HELPERS =====
def find_user(db, email):
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def find_user_by_username(db, username):
    """Usernames are saved in lowercase, so "Asha_K" and "asha_k" are the same name."""
    return db.scalar(select(User).where(User.username == username.strip().lower()))


def code_sent_recently(db, user_id):
    last = db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user_id))
    return last is not None and last > utc_now() - RESEND_WAIT


def codes_sent_today(db, user_id):
    return db.scalar(select(func.count()).select_from(OtpCode).where(
        OtpCode.user_id == user_id, OtpCode.created_at > utc_now() - timedelta(days=1)))


def too_many_codes(db, user_id):
    sent_last_hour = db.scalar(select(func.count(OtpCode.id)).where(
        OtpCode.user_id == user_id, OtpCode.created_at > utc_now() - timedelta(hours=1)))
    return sent_last_hour >= MAX_CODES_PER_HOUR


def mask_email(email):
    """"asha@gmail.com" → "a•••@gmail.com"."""
    name, _, domain = email.partition("@")
    return name[:1] + "•••@" + domain


def demo_mode_on():
    """DEMO_SHOW_OTP=true in backend/.env shows the code on screen. Demo only: must be false in the real app."""
    return (os.getenv("DEMO_SHOW_OTP") or "").strip() == "true"


def deliver_login_code(user, code):
    """The ONE place that sends a login code (Brevo or Gmail, email_sender.py). Couldn't send → 503 EMAIL_FAILED."""
    try:
        send_otp_email(user.email, code)
    except Exception as error:
        print("Email failed:", type(error).__name__, error)  # shows in the server window (never the code)
        raise AppError(503, "EMAIL_FAILED", "We couldn't send the email right now. Please try again in a minute.")


def send_new_code(db, user, ip):
    """Make a new 6-digit code, save its hash, and email it. Older codes stop working.
    Returns {"sent_to", "code"} (the code itself is only shown in demo mode: code_sent_reply).
    A sending problem → 503 and nothing is saved (open_db undoes the new code).
    Max 5 codes per hour → 429 TOO_MANY_CODES. Daily caps (per account and per IP) → 429 TOO_MANY_REQUESTS:
    stops someone flooding a mailbox."""
    if too_many_codes(db, user.id):
        raise AppError(429, "TOO_MANY_CODES", "Too many codes asked for. Please try again in an hour.")
    if codes_sent_today(db, user.id) >= CODES_PER_DAY_PER_ACCOUNT:
        raise rate_limit.too_many(60 * 60)
    rate_limit.check("codes-ip:" + ip, *CODES_PER_DAY_PER_IP)
    code = make_otp()
    db.execute(update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False)).values(used=True))
    db.add(OtpCode(user_id=user.id, code_hash=hash_text(code), expires_at=utc_now() + CODE_LIFETIME))
    deliver_login_code(user, code)
    rate_limit.add("codes-ip:" + ip)  # only codes really sent count
    return {"sent_to": mask_email(user.email), "code": code}


def cookie_is_secure(request):
    """Production: always Secure. Development: only on https, so http://localhost keeps working."""
    return is_production() or request.url.scheme == "https"


def get_current_user(request):
    """The logged-in user (from the session cookie) as {id, full_name, username, email, language}, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with open_db() as db:
        row = db.execute(
            select(User.id, User.email, User.username, Profile.full_name, Profile.language)
            .join(LoginSession, LoginSession.user_id == User.id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(LoginSession.token_hash == hash_text(token), LoginSession.expires_at > utc_now())).first()
    return {"id": row.id, "email": row.email, "username": row.username, "full_name": row.full_name or "",
            "language": row.language} if row else None


def require_user(request: Request):
    """Used by every money route: the logged-in user's id (UUID), or a 401 error if nobody is logged in."""
    user = get_current_user(request)
    if user is None:
        raise AppError(401, "NOT_LOGGED_IN", "Please log in first.")
    return user["id"]


# ===== ROUTES =====
@router.post("/register", status_code=201)
def register(form: RegisterForm, request: Request):
    rate_limit.hit("register-ip:" + rate_limit.client_ip(request), *REGISTER_PER_IP)
    full_name = (form.full_name or "").strip() or None  # optional: the app shows the username instead
    if form.password != form.confirm_password:
        raise AppError(400, "PASSWORDS_DIFFERENT", "The two passwords don't match.")
    problems = get_password_problems(form.password)
    if problems:
        raise AppError(400, "PASSWORD_WEAK", "Your password needs " + ", ".join(problems) + ".")

    with open_db() as db:
        # form.email / form.username are already cleaned in models.py (lowercase)
        if form.email and find_user(db, form.email):
            raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Try logging in.")
        if find_user_by_username(db, form.username):
            raise AppError(409, "USERNAME_TAKEN", "This username is already taken. Please pick another one.")
        user = User(email=form.email, username=form.username, password_hash=hash_password(form.password))
        db.add(user)
        db.flush()  # gives the user its id
        db.add(Profile(user_id=user.id, full_name=full_name))
    return {"message": "Account created! You can log in now.", "code": "ACCOUNT_CREATED"}


@router.post("/login")
def login(form: LoginForm, request: Request):
    """Step 1: check the password. If correct, send a 6-digit code (step 2 is /verify-code)."""
    ip = rate_limit.client_ip(request)
    rate_limit.hit("login-ip:" + ip, *LOGIN_PER_IP)
    rate_limit.hit("login-account:" + form.email.strip().lower(), *LOGIN_PER_ACCOUNT)
    with open_db() as db:
        user = find_user(db, form.email)
        if user is None:
            waste_password_check(form.password)  # same ~1 s wait as a real account: no hint that it doesn't exist
            raise AppError(401, "WRONG_LOGIN", "Wrong email or password.")
        if user.is_locked:
            raise AppError(423, "ACCOUNT_LOCKED", LOCKED_MESSAGE)

        if not password_matches(form.password, user.password_hash):
            tries = user.failed_attempts + 1
            locked = tries >= MAX_PASSWORD_TRIES
            user.failed_attempts, user.is_locked = tries, locked
            db.commit()  # save before raising the error, or the count would be lost
            if locked:
                raise AppError(423, "ACCOUNT_LOCKED", LOCKED_MESSAGE)
            left = MAX_PASSWORD_TRIES - tries
            raise AppError(401, "WRONG_LOGIN_TRIES", f"Wrong email or password. {left} attempt{'s' if left > 1 else ''} left.",
                           {"left": left})

        user.failed_attempts = 0
        db.commit()  # the reset is kept even if sending the code fails
        sent = send_new_code(db, user, ip)
    return code_sent_reply("Password correct. We emailed you a 6-digit code.", "CODE_SENT", sent, show_demo_code=True)


def code_sent_reply(message, code, sent, show_demo_code=False):
    """Tells the code screen how long the code lasts, when Resend works, and where the code went (masked).
    demo_code: only after a correct password (/login) AND DEMO_SHOW_OTP=true. Never from /resend-code: it needs
    no password, so anyone who knows the email could read the code there."""
    reply = {"message": message, "code": code, "expires_in": int(CODE_LIFETIME.total_seconds()),
             "resend_wait": int(RESEND_WAIT.total_seconds()),
             "sent_to": sent["sent_to"]}
    if show_demo_code and demo_mode_on():
        reply["demo_code"] = sent["code"]
    return reply


@router.post("/resend-code")
def resend_code(form: EmailForm, request: Request):
    """Email a fresh code to someone already on the code screen (30-second cooldown)."""
    ip = rate_limit.client_ip(request)
    rate_limit.hit("resend-ip:" + ip, *RESEND_PER_IP)
    with open_db() as db:
        user = find_user(db, form.email)
        last = user and db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user.id))
        if not last or last < utc_now() - RESEND_WINDOW:
            raise AppError(400, "LOGIN_AGAIN", "Please log in again to get a new code.")
        if code_sent_recently(db, user.id):
            raise AppError(429, "RESEND_WAIT", "Please wait a few seconds before asking for another code.")
        sent = send_new_code(db, user, ip)
    return code_sent_reply("We emailed you a new 6-digit code.", "CODE_RESENT", sent)


@router.post("/send-login-code")
def send_login_code(form: EmailForm, request: Request):
    """For locked accounts: email a code that logs in and unlocks the account."""
    ip = rate_limit.client_ip(request)
    rate_limit.hit("resend-ip:" + ip, *RESEND_PER_IP)
    with open_db() as db:
        user = find_user(db, form.email)
        # account's daily cap reached → quietly send nothing (an error would show the account exists)
        if (user and user.is_locked and not code_sent_recently(db, user.id)
                and codes_sent_today(db, user.id) < CODES_PER_DAY_PER_ACCOUNT):
            try:
                send_new_code(db, user, ip)
            except AppError as error:  # too many codes / sending failed: the reply stays the same
                db.rollback()  # the unsent code is not kept
                print("Locked-account code not sent:", error.code)
    # Same reply every time (no masked email, no demo code), so nobody can use this to check
    # which emails have accounts or are locked
    return {"message": "If this account is locked, we've sent a login code to its email.",
            "code": "LOCKED_CODE_SENT"}


@router.post("/verify-code")
def verify_code(form: CodeForm, request: Request, response: Response):
    """Step 2: check the emailed code. If correct, log in (and unlock the account)."""
    ip = rate_limit.client_ip(request)
    rate_limit.hit("verify-ip:" + ip, *VERIFY_PER_IP)
    rate_limit.check("wrong-code-ip:" + ip, *WRONG_CODES_PER_IP)  # M1: wrong guesses are counted per IP too
    with open_db() as db:
        user = find_user(db, form.email)
        code_row = None
        if user:
            code_row = db.scalar(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False))
                                 .order_by(OtpCode.created_at.desc()).limit(1))
        if code_row is None:
            raise AppError(400, "LOGIN_AGAIN", "Please log in again to get a new code.")
        if code_row.expires_at < utc_now():
            raise AppError(410, "CODE_EXPIRED", "Your code has expired. Please request a new one.")
        wrong_last_hour = db.scalar(select(func.coalesce(func.sum(OtpCode.attempts), 0)).where(
            OtpCode.user_id == user.id, OtpCode.created_at > utc_now() - timedelta(hours=1)))
        if wrong_last_hour >= MAX_CODE_TRIES_PER_HOUR:  # stops guessing codes by asking for new ones again and again
            raise AppError(429, "TOO_MANY_CODE_TRIES", "Too many wrong codes. Please try again in an hour.")

        if not same_hash(code_row.code_hash, hash_text(form.code)):
            code_row.attempts += 1
            code_row.used = code_row.attempts >= MAX_CODE_TRIES
            db.commit()
            rate_limit.add("wrong-code-ip:" + ip)
            raise AppError(400, "WRONG_CODE", "Wrong code. Please check your messages and try again.")

        token = make_session_token()
        code_row.used = True
        user.failed_attempts, user.is_locked = 0, False
        db.add(LoginSession(token_hash=hash_text(token), user_id=user.id, expires_at=utc_now() + SESSION_LIFETIME))

    # httponly = JavaScript can't read the cookie, so a bad script can't steal it.
    # secure = only sent over https: always in production (Render's proxy talks http to us), so don't trust the scheme
    response.set_cookie(COOKIE_NAME, token, max_age=int(SESSION_LIFETIME.total_seconds()), httponly=True,
                        samesite="lax", secure=cookie_is_secure(request))
    return {"message": "Logged in.", "code": "LOGGED_IN"}


@router.get("/me")
def me(request: Request):
    user = get_current_user(request)
    if user is None:
        raise AppError(401, "NOT_LOGGED_IN", "Not logged in.")
    return {"full_name": user["full_name"], "username": user["username"], "email": user["email"],
            "language": user["language"]}


@router.put("/language")
def save_language(form: LanguageForm, user_id=Depends(require_user)):  # login checked first -> 401 before 422
    """Remembers the chosen language on the account, so it follows the user to other devices."""
    with open_db() as db:
        db.execute(update(Profile).where(Profile.user_id == user_id).values(language=form.language))
    return {"language": form.language}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with open_db() as db:
            db.execute(delete(LoginSession).where(LoginSession.token_hash == hash_text(token)))
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax", secure=cookie_is_secure(request))
    return {"message": "Logged out.", "code": "LOGGED_OUT"}
