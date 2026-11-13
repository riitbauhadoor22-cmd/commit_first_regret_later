# test_otp.py — tests for the login code (OTP): valid code, expiry, wrong guesses, codes never stored
# in plain text, and the locked-account flow (3 wrong passwords -> "Send me a login code").
from sqlalchemy import select

import database
from conftest import PASSWORD, age_codes, register
from models import OtpCode, User

EMAIL = "asha@example.com"


def start_login(client):
    res = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert res.status_code == 200


def verify(client, code):
    return client.post("/api/auth/verify-code", json={"email": EMAIL, "code": code})


# ===== CODES =====
def test_valid_code_logs_in(client, sent_codes):
    register(client)
    start_login(client)
    assert verify(client, sent_codes[-1]).status_code == 200
    assert client.get("/api/auth/me").json() == {"full_name": "Asha", "email": EMAIL, "language": None}


def test_expired_code_is_refused(client, sent_codes):
    register(client)
    start_login(client)
    age_codes(5 * 60 + 1)  # just over 5 minutes later
    res = verify(client, sent_codes[-1])
    assert res.status_code == 410
    assert "expired" in res.json()["detail"]


def test_resend_sends_new_code_and_restarts_timer(client, sent_codes):
    register(client)
    start_login(client)
    age_codes(5 * 60 + 1)  # the first code has expired
    res = client.post("/api/auth/resend-code", json={"email": "asha@example.com"})
    assert res.status_code == 200 and res.json()["expires_in"] == 300
    assert len(sent_codes) == 2
    assert verify(client, sent_codes[-1]).status_code == 200  # the new code works


def test_resend_has_30_second_cooldown(client, sent_codes):
    register(client)
    start_login(client)
    res = client.post("/api/auth/resend-code", json={"email": "asha@example.com"})
    assert res.status_code == 429
    assert len(sent_codes) == 1  # no extra email sent


def test_resend_without_login_step_is_refused(client, sent_codes):
    register(client)
    res = client.post("/api/auth/resend-code", json={"email": "asha@example.com"})
    assert res.status_code == 400
    assert sent_codes == []


def test_code_stops_working_after_5_wrong_guesses(client, sent_codes):
    register(client)
    start_login(client)
    wrong = "000000" if sent_codes[-1] != "000000" else "111111"
    for _ in range(5):
        assert verify(client, wrong).status_code == 400
    assert verify(client, sent_codes[-1]).status_code == 400


def test_new_login_replaces_old_code(client, sent_codes):
    register(client)
    start_login(client)
    old = sent_codes[-1]
    start_login(client)
    if old != sent_codes[-1]:  # (1 in a million chance they match)
        assert verify(client, old).status_code == 400
    assert verify(client, sent_codes[-1]).status_code == 200


def test_codes_and_passwords_are_only_stored_as_hashes(client, sent_codes):
    register(client)
    start_login(client)
    with database.open_db() as db:
        user = db.scalar(select(User))
        code = db.scalar(select(OtpCode))
        assert user.password_hash != PASSWORD and user.password_hash.startswith("$2")
        assert code.code_hash != sent_codes[-1] and len(code.code_hash) == 64


def test_email_is_saved_in_lowercase(client):
    register(client, "Asha.Mixed@Example.COM")
    with database.open_db() as db:
        assert db.scalar(select(User.email)) == "asha.mixed@example.com"


# ===== LOCKED ACCOUNT =====
def test_three_wrong_passwords_lock_then_code_unlocks(client, sent_codes):
    register(client)
    for _ in range(2):
        assert client.post("/api/auth/login", json={"email": EMAIL, "password": "Wrong!Pass1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": "Wrong!Pass1"}).status_code == 423
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 423

    assert client.post("/api/auth/send-login-code", json={"email": EMAIL}).status_code == 200
    assert len(sent_codes) == 1
    assert verify(client, sent_codes[-1]).status_code == 200
    with database.open_db() as db:
        assert db.scalar(select(User.is_locked)) is False


def test_send_login_code_for_unknown_email_sends_nothing(client, sent_codes):
    assert client.post("/api/auth/send-login-code", json={"email": "nobody@example.com"}).status_code == 200
    assert sent_codes == []
