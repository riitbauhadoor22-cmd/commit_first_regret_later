# test_auth.py — register, log in, /api/auth/me, and email sending (always faked: no real email is ever sent).
import smtplib

import pytest

import email_sender
import routes.auth
from conftest import PASSWORD, log_in, register

REGISTER = "/api/auth/register"


def form(**changes):
    return {"full_name": "Asha", "email": "asha@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, **changes}


# ===== REGISTER =====
def test_register_valid(client):  # a good form creates the account
    res = client.post(REGISTER, json=form())
    assert res.status_code == 201 and res.json()["code"] == "ACCOUNT_CREATED"


def test_register_duplicate_email(client):  # same email twice (any case) -> 409 EMAIL_TAKEN
    register(client)
    res = client.post(REGISTER, json=form(email="ASHA@example.com"))
    assert res.status_code == 409 and res.json()["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize("missing", ["full_name", "email", "password", "confirm_password"])
def test_register_missing_field(client, missing):  # each missing field -> 422, never 500
    body = form()
    del body[missing]
    assert client.post(REGISTER, json=body).status_code == 422


@pytest.mark.parametrize("password", ["short1!", "alllowercase1!", "ALLUPPER1!", "NoNumber!!", "NoSymbol123"])
def test_register_weak_password(client, password):  # each missing password rule -> 400 PASSWORD_WEAK
    res = client.post(REGISTER, json=form(password=password, confirm_password=password))
    assert res.status_code == 400 and res.json()["code"] == "PASSWORD_WEAK"


def test_register_passwords_different_and_blank_name(client):  # mismatch / spaces-only name -> 400
    assert client.post(REGISTER, json=form(confirm_password=PASSWORD + "x")).json()["code"] == "PASSWORDS_DIFFERENT"
    assert client.post(REGISTER, json=form(full_name="   ")).json()["code"] == "NAME_REQUIRED"


def test_register_bad_email(client):  # not an email -> 422 INVALID_EMAIL
    res = client.post(REGISTER, json=form(email="not-an-email"))
    assert res.status_code == 422 and res.json()["code"] == "INVALID_EMAIL"


# ===== LOGIN =====
def test_login_correct_password_sends_code(client, sent_codes):  # right password -> 200 + one (fake) email
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 200 and res.json()["code"] == "CODE_SENT" and len(sent_codes) == 1


def test_login_wrong_password(client, sent_codes):  # wrong password -> 401, no email sent
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "Wrong!Pass1"})
    assert res.status_code == 401 and sent_codes == []


def test_login_unknown_email(client, sent_codes):  # unknown email -> same 401 "wrong email or password"
    res = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert res.status_code == 401 and res.json()["code"] == "WRONG_LOGIN" and sent_codes == []


# ===== /me =====
def test_me_without_session(client):  # no cookie -> 401
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_session_and_after_logout(client, sent_codes):  # logged in -> name + email; logged out -> 401
    log_in(client, sent_codes)
    assert client.get("/api/auth/me").json() == {"full_name": "Asha", "email": "asha@example.com", "language": None}
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_fake_cookie(client):  # a made-up session token -> 401
    client.cookies.set("session", "made-up-token")
    assert client.get("/api/auth/me").status_code == 401


# ===== EMAIL =====
@pytest.fixture
def no_real_smtp(monkeypatch):
    """Safety net: if any test reached the real Gmail server, fail instead of sending."""
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to connect to Gmail")
    monkeypatch.setattr(smtplib, "SMTP_SSL", refuse)


def test_gmail_not_set_up_gives_clear_error(client, monkeypatch, no_real_smtp):  # empty Gmail settings -> 503, not a crash
    monkeypatch.setenv("GMAIL_ADDRESS", "")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 503 and res.json()["code"] == "EMAIL_FAILED"


def test_send_otp_email_raises_when_not_set_up(monkeypatch, no_real_smtp):  # the sender itself explains what's missing
    monkeypatch.setenv("GMAIL_ADDRESS", "")
    with pytest.raises(RuntimeError, match="Gmail is not set up"):
        email_sender.send_otp_email("asha@example.com", "123456")


def test_email_is_built_correctly_without_sending(monkeypatch):  # a fake SMTP server receives the message
    sent = []

    class FakeSmtp:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def login(self, user, password): sent.append(("login", user))
        def send_message(self, message): sent.append(("send", message["To"], message["Subject"]))

    monkeypatch.setenv("GMAIL_ADDRESS", "app@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh")
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    email_sender.send_otp_email("asha@example.com", "123456")
    assert sent == [("login", "app@example.com"), ("send", "asha@example.com", "Your login code: 123456")]


def test_routes_use_the_mocked_sender(sent_codes):  # the fixture really replaced the Gmail sender
    assert routes.auth.send_otp_email is not email_sender.send_otp_email
