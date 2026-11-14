# routes/auth.py — register (name, username, email and/or phone, password), log in (email OR phone + password, then a
# 6-digit code sent by deliver_login_code: by email when the account has one, otherwise by WhatsApp through the
# Twilio sandbox, whatsapp_sender.py), unlock a locked account, log out. The username is never used to log in.
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, update

from database import open_db
from errors import AppError
from email_sender import send_otp_email
from whatsapp_sender import WhatsAppFailed, WhatsAppNotConfigured, send_otp_whatsapp
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
SESSION_LIFETIME = timedelta(days=7)  # stay logged in for 7 days
COOKIE_NAME = "session"
LOCKED_MESSAGE = "Your account is locked after 3 wrong passwords. Tap 'Send me a login code'."


# ===== HELPERS =====
def find_user(db, login_id):
    """The account for an email ("asha@x.com") or a normalised phone number ("+2305…"), or None."""
    login_id = login_id.strip().lower()
    if "@" in login_id:
        return db.scalar(select(User).where(User.email == login_id))
    return find_user_by_phone(db, login_id)


def find_user_by_phone(db, phone):
    return db.scalar(select(User).join(Profile, Profile.user_id == User.id).where(Profile.phone == phone))


def find_user_by_username(db, username):
    """Usernames are saved in lowercase, so "Asha_K" and "asha_k" are the same name."""
    return db.scalar(select(User).where(User.username == username.strip().lower()))


def code_sent_recently(db, user_id):
    last = db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user_id))
    return last is not None and last > utc_now() - RESEND_WAIT


def deliver_login_code(user, code, phone):
    """The ONE place that decides where a login code goes. Returns "email" or "whatsapp".
    Accounts with an email → Gmail (email_sender.py). Phone-only accounts → WhatsApp (whatsapp_sender.py, Twilio sandbox).
    Twilio keys missing → 503 PHONE_CODE_NOT_AVAILABLE; Twilio couldn't send → 503 WHATSAPP_FAILED."""
    if not user.email:
        try:
            send_otp_whatsapp(phone, code)
        except WhatsAppNotConfigured:
            raise AppError(503, "PHONE_CODE_NOT_AVAILABLE",
                           "WhatsApp login codes aren't set up on this server yet. Please log in with email.")
        except WhatsAppFailed:
            raise AppError(503, "WHATSAPP_FAILED", "We couldn't send the code on WhatsApp. Make sure this phone has "
                           "joined the app's WhatsApp sandbox, then try again.")
        return "whatsapp"
    try:
        send_otp_email(user.email, code)
    except Exception as error:
        print("Email failed:", type(error).__name__, error)  # shows in the server window (never the code)
        raise AppError(503, "EMAIL_FAILED", "We couldn't send the email right now. Please try again in a minute.")
    return "email"


def send_new_code(db, user):
    """Make a new 6-digit code, save its hash, and send it. Older codes stop working. Returns "email" or "whatsapp".
    A sending problem → 503 and nothing is saved (open_db undoes the new code)."""
    code = make_otp()
    db.execute(update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False)).values(used=True))
    db.add(OtpCode(user_id=user.id, code_hash=hash_text(code), expires_at=utc_now() + CODE_LIFETIME))
    phone = db.scalar(select(Profile.phone).where(Profile.user_id == user.id))
    return deliver_login_code(user, code, phone)


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
def register(form: RegisterForm):
    full_name = (form.full_name or "").strip() or None  # optional: the app shows the username instead
    if form.password != form.confirm_password:
        raise AppError(400, "PASSWORDS_DIFFERENT", "The two passwords don't match.")
    problems = get_password_problems(form.password)
    if problems:
        raise AppError(400, "PASSWORD_WEAK", "Your password needs " + ", ".join(problems) + ".")

    with open_db() as db:
        # form.email / form.phone / form.username are already cleaned in models.py (lowercase, +230…)
        if form.email and find_user(db, form.email):
            raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Try logging in.")
        if form.phone and find_user_by_phone(db, form.phone):
            raise AppError(409, "PHONE_TAKEN", "An account with this phone number already exists. Try logging in.")
        if find_user_by_username(db, form.username):
            raise AppError(409, "USERNAME_TAKEN", "This username is already taken. Please pick another one.")
        user = User(email=form.email, username=form.username, password_hash=hash_password(form.password))
        db.add(user)
        db.flush()  # gives the user its id
        db.add(Profile(user_id=user.id, full_name=full_name, phone=form.phone))  # phone: "+230…" or None
    return {"message": "Account created! You can log in now.", "code": "ACCOUNT_CREATED"}


@router.post("/login")
def login(form: LoginForm):
    """Step 1: check the password. If correct, send a 6-digit code (step 2 is /verify-code). form.email = email or phone."""
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
        channel = send_new_code(db, user)
    if channel == "whatsapp":
        return code_sent_reply("Password correct. We sent a 6-digit code to your WhatsApp.", "CODE_SENT_WHATSAPP")
    return code_sent_reply("Password correct. We emailed you a 6-digit code.", "CODE_SENT")


def code_sent_reply(message, code):
    """Tells the code screen how long the code lasts and how long until Resend works."""
    return {"message": message, "code": code, "expires_in": int(CODE_LIFETIME.total_seconds()),
            "resend_wait": int(RESEND_WAIT.total_seconds())}


@router.post("/resend-code")
def resend_code(form: EmailForm):
    """Email a fresh code to someone already on the code screen (30-second cooldown)."""
    with open_db() as db:
        user = find_user(db, form.email)
        last = user and db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user.id))
        if not last or last < utc_now() - RESEND_WINDOW:
            raise AppError(400, "LOGIN_AGAIN", "Please log in again to get a new code.")
        if code_sent_recently(db, user.id):
            raise AppError(429, "RESEND_WAIT", "Please wait a few seconds before asking for another code.")
        channel = send_new_code(db, user)
    if channel == "whatsapp":
        return code_sent_reply("We sent a new 6-digit code to your WhatsApp.", "CODE_RESENT_WHATSAPP")
    return code_sent_reply("We emailed you a new 6-digit code.", "CODE_RESENT")


@router.post("/send-login-code")
def send_login_code(form: EmailForm):
    """For locked accounts: email a code that logs in and unlocks the account."""
    with open_db() as db:
        user = find_user(db, form.email)
        if user and user.is_locked and not code_sent_recently(db, user.id):
            send_new_code(db, user)
    # Same reply every time, so nobody can use this to check which emails / phones have accounts
    return {"message": "If this account is locked, we've sent a login code to its email or phone.",
            "code": "LOCKED_CODE_SENT"}


@router.post("/verify-code")
def verify_code(form: CodeForm, request: Request, response: Response):
    """Step 2: check the emailed code. If correct, log in (and unlock the account)."""
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
            raise AppError(400, "WRONG_CODE", "Wrong code. Please check your messages and try again.")

        token = make_session_token()
        code_row.used = True
        user.failed_attempts, user.is_locked = 0, False
        db.add(LoginSession(token_hash=hash_text(token), user_id=user.id, expires_at=utc_now() + SESSION_LIFETIME))

    # httponly = JavaScript can't read the cookie, so a bad script can't steal it
    response.set_cookie(COOKIE_NAME, token, max_age=int(SESSION_LIFETIME.total_seconds()), httponly=True,
                        samesite="lax", secure=request.url.scheme == "https")
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
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out.", "code": "LOGGED_OUT"}
