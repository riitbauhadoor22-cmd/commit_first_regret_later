# security.py — password rules, bcrypt hashing, 6-digit login codes (OTP) and session tokens.
import hashlib
import re
import secrets

import bcrypt

BCRYPT_ROUNDS = 14  # slow on purpose (~1 second) so stolen hashes are hard to crack


def get_password_problems(password):
    """Return a list of what the password is missing. Empty list = password is OK.
    Same rules as the strength meter in frontend/login.js."""
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        problems.append("a capital letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol (like ! @ #)")
    if len(password.encode("utf-8")) > 72:  # bcrypt can only use the first 72 bytes
        problems.append("at most 72 characters")
    return problems


def hash_password(password):
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def password_matches(password, password_hash):
    """Like check_password, but never crashes: bcrypt refuses passwords over 72 bytes, so those are simply wrong."""
    try:
        return check_password(password, password_hash)
    except ValueError:
        return False


_dummy_hash = None


def waste_password_check(password):
    """Same slow bcrypt work as a real check, for logins with an unknown email/phone,
    so the reply time doesn't tell an attacker which accounts exist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("Not-a-real-password-1")
    password_matches(password, _dummy_hash)


def make_otp():
    """A random 6-digit code, e.g. "042917"."""
    return f"{secrets.randbelow(1_000_000):06d}"


def make_session_token():
    return secrets.token_urlsafe(32)


def hash_text(text):
    """SHA-256 hash, used for codes and session tokens so the database never holds the real ones."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_hash(a, b):
    return secrets.compare_digest(a, b)  # compares without leaking timing information
