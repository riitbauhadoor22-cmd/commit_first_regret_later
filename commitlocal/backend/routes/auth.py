# routes/auth.py — register, log in (password + emailed 6-digit code), unlock a locked account, log out.
import time

from fastapi import APIRouter, HTTPException, Request, Response

from database import open_db
from email_sender import send_otp_email
from models import CodeForm, EmailForm, LoginForm, RegisterForm
from security import (check_password, get_password_problems, hash_password, hash_text,
                      make_otp, make_session_token, same_hash)

router = APIRouter(prefix="/api/auth")

MAX_PASSWORD_TRIES = 3
MAX_CODE_TRIES = 5                 # wrong guesses allowed per code
CODE_LIFETIME = 5 * 60             # 5 minutes
RESEND_WAIT = 60                   # seconds before a new code can be sent
SESSION_LIFETIME = 7 * 24 * 3600   # stay logged in for 7 days
COOKIE_NAME = "session"
LOCKED_MESSAGE = "Your account is locked after 3 wrong passwords. Tap 'Send me a login code'."


# ===== HELPERS =====
def find_user(db, email):
    return db.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def code_sent_recently(db, user_id):
    row = db.execute("SELECT MAX(created_at) AS last FROM otp_codes WHERE user_id = ?", (user_id,)).fetchone()
    return row["last"] is not None and row["last"] > time.time() - RESEND_WAIT


def send_new_code(db, user):
    """Make a new 6-digit code, save its hash, and email it. Older codes stop working."""
    now = int(time.time())
    code = make_otp()
    db.execute("UPDATE otp_codes SET used = 1 WHERE user_id = ? AND used = 0", (user["id"],))
    db.execute("INSERT INTO otp_codes (user_id, code_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
               (user["id"], hash_text(code), now + CODE_LIFETIME, now))
    try:
        send_otp_email(user["email"], code)
    except Exception as error:
        print("Email failed:", error)  # shows in the server window
        raise HTTPException(503, "We couldn't send the email right now. Please try again in a minute.")


def get_current_user(request):
    """The logged-in user (from the session cookie), or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with open_db() as db:
        return db.execute(
            "SELECT users.id, full_name, email FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE token_hash = ? AND expires_at > ?", (hash_text(token), int(time.time()))).fetchone()


# ===== ROUTES =====
@router.post("/register", status_code=201)
def register(form: RegisterForm):
    full_name = form.full_name.strip()
    if not full_name:
        raise HTTPException(400, "Please enter your full name.")
    if form.password != form.confirm_password:
        raise HTTPException(400, "The two passwords don't match.")
    problems = get_password_problems(form.password)
    if problems:
        raise HTTPException(400, "Your password needs " + ", ".join(problems) + ".")

    with open_db() as db:
        if find_user(db, form.email):
            raise HTTPException(409, "An account with this email already exists. Try logging in.")
        db.execute("INSERT INTO users (full_name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                   (full_name, form.email.strip().lower(), hash_password(form.password), int(time.time())))
    return {"message": "Account created! You can log in now."}


@router.post("/login")
def login(form: LoginForm):
    """Step 1: check the password. If correct, email a 6-digit code (step 2 is /verify-code)."""
    with open_db() as db:
        user = find_user(db, form.email)
        if user is None:
            raise HTTPException(401, "Wrong email or password.")
        if user["is_locked"]:
            raise HTTPException(423, LOCKED_MESSAGE)

        if not check_password(form.password, user["password_hash"]):
            tries = user["failed_attempts"] + 1
            locked = tries >= MAX_PASSWORD_TRIES
            db.execute("UPDATE users SET failed_attempts = ?, is_locked = ? WHERE id = ?",
                       (tries, int(locked), user["id"]))
            db.commit()  # save before raising the error, or the count would be lost
            if locked:
                raise HTTPException(423, LOCKED_MESSAGE)
            left = MAX_PASSWORD_TRIES - tries
            raise HTTPException(401, f"Wrong email or password. {left} attempt{'s' if left > 1 else ''} left.")

        db.execute("UPDATE users SET failed_attempts = 0 WHERE id = ?", (user["id"],))
        send_new_code(db, user)
    return {"message": "Password correct. We emailed you a 6-digit code."}


@router.post("/send-login-code")
def send_login_code(form: EmailForm):
    """For locked accounts: email a code that logs in and unlocks the account."""
    with open_db() as db:
        user = find_user(db, form.email)
        if user and user["is_locked"] and not code_sent_recently(db, user["id"]):
            send_new_code(db, user)
    # Same reply every time, so nobody can use this to check which emails have accounts
    return {"message": "If this account is locked, we've emailed a login code. Check your inbox."}


@router.post("/verify-code")
def verify_code(form: CodeForm, request: Request, response: Response):
    """Step 2: check the emailed code. If correct, log in (and unlock the account)."""
    now = int(time.time())
    with open_db() as db:
        user = find_user(db, form.email)
        code_row = None
        if user:
            code_row = db.execute("SELECT * FROM otp_codes WHERE user_id = ? AND used = 0 ORDER BY id DESC LIMIT 1",
                                  (user["id"],)).fetchone()
        if code_row is None or code_row["expires_at"] < now:
            raise HTTPException(400, "This code has expired. Please log in again to get a new one.")

        if not same_hash(code_row["code_hash"], hash_text(form.code)):
            tries = code_row["tries"] + 1
            db.execute("UPDATE otp_codes SET tries = ?, used = ? WHERE id = ?",
                       (tries, int(tries >= MAX_CODE_TRIES), code_row["id"]))
            db.commit()
            raise HTTPException(400, "Wrong code. Please check your email and try again.")

        token = make_session_token()
        db.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (code_row["id"],))
        db.execute("UPDATE users SET failed_attempts = 0, is_locked = 0 WHERE id = ?", (user["id"],))
        db.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                   (hash_text(token), user["id"], now + SESSION_LIFETIME))

    # httponly = JavaScript can't read the cookie, so a bad script can't steal it
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_LIFETIME, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https")
    return {"message": "Logged in."}


@router.get("/me")
def me(request: Request):
    user = get_current_user(request)
    if user is None:
        raise HTTPException(401, "Not logged in.")
    return {"full_name": user["full_name"], "email": user["email"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with open_db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_text(token),))
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out."}
