# routes/auth.py — register, log in (password + emailed 6-digit code), unlock a locked account, log out.
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, update

from database import open_db
from errors import AppError
from email_sender import send_otp_email
from models import CodeForm, EmailForm, LanguageForm, LoginForm, LoginSession, OtpCode, Profile, RegisterForm, User, utc_now
from security import (check_password, get_password_problems, hash_password, hash_text,
                      make_otp, make_session_token, same_hash)

router = APIRouter(prefix="/api/auth")

MAX_PASSWORD_TRIES = 3
MAX_CODE_TRIES = 5                 # wrong guesses allowed per code
CODE_LIFETIME = timedelta(minutes=5)
RESEND_WAIT = timedelta(seconds=30)  # before a new code can be sent
RESEND_WINDOW = timedelta(minutes=30)  # "Resend" only works if a code was sent this recently
SESSION_LIFETIME = timedelta(days=7)  # stay logged in for 7 days
COOKIE_NAME = "session"
LOCKED_MESSAGE = "Your account is locked after 3 wrong passwords. Tap 'Send me a login code'."


# ===== HELPERS =====
def find_user(db, email):
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def code_sent_recently(db, user_id):
    last = db.scalar(select(func.max(OtpCode.created_at)).where(OtpCode.user_id == user_id))
    return last is not None and last > utc_now() - RESEND_WAIT


def send_new_code(db, user):
    """Make a new 6-digit code, save its hash, and email it. Older codes stop working."""
    code = make_otp()
    db.execute(update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False)).values(used=True))
    db.add(OtpCode(user_id=user.id, code_hash=hash_text(code), expires_at=utc_now() + CODE_LIFETIME))
    try:
        send_otp_email(user.email, code)
    except Exception as error:
        print("Email failed:", error)  # shows in the server window
        raise AppError(503, "EMAIL_FAILED", "We couldn't send the email right now. Please try again in a minute.")


def get_current_user(request):
    """The logged-in user (from the session cookie) as {id, full_name, email}, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with open_db() as db:
        row = db.execute(
            select(User.id, User.email, Profile.full_name, Profile.language)
            .join(LoginSession, LoginSession.user_id == User.id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(LoginSession.token_hash == hash_text(token), LoginSession.expires_at > utc_now())).first()
    return {"id": row.id, "email": row.email, "full_name": row.full_name or "",
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
    full_name = form.full_name.strip()
    if not full_name:
        raise AppError(400, "NAME_REQUIRED", "Please enter your full name.")
    if form.password != form.confirm_password:
        raise AppError(400, "PASSWORDS_DIFFERENT", "The two passwords don't match.")
    problems = get_password_problems(form.password)
    if problems:
        raise AppError(400, "PASSWORD_WEAK", "Your password needs " + ", ".join(problems) + ".")

    with open_db() as db:
        if find_user(db, form.email):
            raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Try logging in.")
        user = User(email=form.email.strip().lower(), password_hash=hash_password(form.password))
        db.add(user)
        db.flush()  # gives the user its id
        db.add(Profile(user_id=user.id, full_name=full_name))
    return {"message": "Account created! You can log in now.", "code": "ACCOUNT_CREATED"}


@router.post("/login")
def login(form: LoginForm):
    """Step 1: check the password. If correct, email a 6-digit code (step 2 is /verify-code)."""
    with open_db() as db:
        user = find_user(db, form.email)
        if user is None:
            raise AppError(401, "WRONG_LOGIN", "Wrong email or password.")
        if user.is_locked:
            raise AppError(423, "ACCOUNT_LOCKED", LOCKED_MESSAGE)

        if not check_password(form.password, user.password_hash):
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
        send_new_code(db, user)
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
        send_new_code(db, user)
    return code_sent_reply("We emailed you a new 6-digit code.", "CODE_RESENT")


@router.post("/send-login-code")
def send_login_code(form: EmailForm):
    """For locked accounts: email a code that logs in and unlocks the account."""
    with open_db() as db:
        user = find_user(db, form.email)
        if user and user.is_locked and not code_sent_recently(db, user.id):
            send_new_code(db, user)
    # Same reply every time, so nobody can use this to check which emails have accounts
    return {"message": "If this account is locked, we've emailed a login code. Check your inbox.", "code": "LOCKED_CODE_SENT"}


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

        if not same_hash(code_row.code_hash, hash_text(form.code)):
            code_row.attempts += 1
            code_row.used = code_row.attempts >= MAX_CODE_TRIES
            db.commit()
            raise AppError(400, "WRONG_CODE", "Wrong code. Please check your email and try again.")

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
    return {"full_name": user["full_name"], "email": user["email"], "language": user["language"]}


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
