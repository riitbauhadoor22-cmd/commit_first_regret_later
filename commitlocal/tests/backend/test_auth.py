# test_auth.py — register, log in, /api/auth/me, and email sending (always faked: no real email is ever sent).
import smtplib

import pytest
from sqlalchemy import select

import database
import email_sender
import routes.auth
from conftest import PASSWORD, age_codes, log_in, register
from models import Profile, User

REGISTER = "/api/auth/register"


def form(**changes):
    return {"full_name": "Asha", "username": "asha_k", "email": "asha@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, **changes}


# ===== REGISTER =====
def test_register_valid(client):  # a good form creates the account
    res = client.post(REGISTER, json=form())
    assert res.status_code == 201 and res.json()["code"] == "ACCOUNT_CREATED"


def test_register_duplicate_email(client):  # same email twice (any case) -> 409 EMAIL_TAKEN
    register(client)
    res = client.post(REGISTER, json=form(email="ASHA@example.com"))
    assert res.status_code == 409 and res.json()["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize("missing", ["username", "email", "password", "confirm_password"])
def test_register_missing_field(client, missing):  # each missing field -> 422, never 500
    body = form()
    del body[missing]
    assert client.post(REGISTER, json=body).status_code == 422


@pytest.mark.parametrize("password", ["short1!", "alllowercase1!", "ALLUPPER1!", "NoNumber!!", "NoSymbol123"])
def test_register_weak_password(client, password):  # each missing password rule -> 400 PASSWORD_WEAK
    res = client.post(REGISTER, json=form(password=password, confirm_password=password))
    assert res.status_code == 400 and res.json()["code"] == "PASSWORD_WEAK"


def test_register_passwords_different(client):  # mismatch -> 400
    assert client.post(REGISTER, json=form(confirm_password=PASSWORD + "x")).json()["code"] == "PASSWORDS_DIFFERENT"


def test_register_works_without_full_name(client):  # the Full name field was removed; old clients may still send it
    body = form()
    del body["full_name"]
    assert client.post(REGISTER, json=body).status_code == 201
    assert client.post(REGISTER, json=form(full_name="   ", username="asha_b", email="b@example.com")).status_code == 201


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
    assert client.get("/api/auth/me").json() == {"full_name": "Asha", "username": "asha_example.com",
                                                 "email": "asha@example.com", "language": None}
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


# ===== USERNAME + PHONE AT REGISTRATION =====
def saved_account(email="asha@example.com"):
    """(username, phone) as stored in the database."""
    with database.open_db() as db:
        user = db.scalar(select(User).where(User.email == email))
        profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
        return user.username, profile.phone


def test_register_with_username_and_phone(client):  # both saved: username lowercase, phone as +230XXXXXXXX
    res = client.post(REGISTER, json=form(username="  Asha_K  ", phone="5123 4567"))
    assert res.status_code == 201
    assert saved_account() == ("asha_k", "+23051234567")


def test_register_without_phone(client):  # the phone number is optional (missing or empty)
    assert client.post(REGISTER, json=form()).status_code == 201
    assert client.post(REGISTER, json=form(email="b@example.com", username="bobby", phone="")).status_code == 201
    assert saved_account()[1] is None and saved_account("b@example.com")[1] is None


@pytest.mark.parametrize("phone, saved", [("+230 5123 4567", "+23051234567"), ("+230-212-3456", "+2302123456"),
                                          ("2123456", "+2302123456"), ("51234567", "+23051234567")])
def test_register_phone_is_normalised(client, phone, saved):  # spaces / dashes removed, +230 added
    assert client.post(REGISTER, json=form(phone=phone)).status_code == 201
    assert saved_account()[1] == saved


@pytest.mark.parametrize("phone", ["12345", "61234567", "+44 7700 900123", "abcdefg", "+230 5123 45678", "5123456a"])
def test_register_invalid_phone(client, phone):  # not a Mauritius number -> 422 INVALID_PHONE, nothing saved
    res = client.post(REGISTER, json=form(phone=phone))
    assert res.status_code == 422 and res.json()["code"] == "INVALID_PHONE"
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 401


@pytest.mark.parametrize("username", ["", "ab", "a" * 31, "asha k", "asha@k", "ásha", "   "])
def test_register_invalid_username(client, username):  # 3–30 of letters, digits . _ - only, else 422 INVALID_USERNAME
    res = client.post(REGISTER, json=form(username=username))
    assert res.status_code == 422 and res.json()["code"] == "INVALID_USERNAME"


def test_register_duplicate_username_any_case(client):  # same username (other case) -> 409 USERNAME_TAKEN
    assert client.post(REGISTER, json=form(username="Asha_K")).status_code == 201
    res = client.post(REGISTER, json=form(email="other@example.com", username="ASHA_k"))
    assert res.status_code == 409 and res.json()["code"] == "USERNAME_TAKEN"


# ===== EMAIL OR PHONE (at least one) =====
def phone_only(**changes):
    body = form(email=None, phone="5123 4567", **changes)
    del body["email"]
    return body


def test_register_email_only_phone_only_or_both(client):
    assert client.post(REGISTER, json=form()).status_code == 201
    assert client.post(REGISTER, json=phone_only(username="phone_only")).status_code == 201
    assert client.post(REGISTER, json=form(email="both@example.com", username="both", phone="52223333")).status_code == 201
    with database.open_db() as db:
        user = db.scalar(select(User).where(User.username == "phone_only"))
        assert user.email is None
        assert db.scalar(select(Profile.phone).where(Profile.user_id == user.id)) == "+23051234567"


@pytest.mark.parametrize("email, phone", [(None, None), ("", ""), ("  ", None)])
def test_register_needs_email_or_phone(client, email, phone):  # neither -> 422 EMAIL_OR_PHONE_REQUIRED
    res = client.post(REGISTER, json=form(email=email, phone=phone))
    assert res.status_code == 422 and res.json()["code"] == "EMAIL_OR_PHONE_REQUIRED"


def test_register_duplicate_phone(client):  # same number written differently -> 409 PHONE_TAKEN
    assert client.post(REGISTER, json=form(phone="51234567")).status_code == 201
    res = client.post(REGISTER, json=form(email="b@example.com", username="bobby", phone="+230 5123-4567"))
    assert res.status_code == 409 and res.json()["code"] == "PHONE_TAKEN"


def test_login_with_phone_sends_the_code_by_email(client, sent_codes):  # an account with both: phone works as login
    client.post(REGISTER, json=form(phone="51234567"))
    res = client.post("/api/auth/login", json={"email": "5123 4567", "password": PASSWORD})
    assert res.status_code == 200 and res.json()["code"] == "CODE_SENT" and len(sent_codes) == 1
    res = client.post("/api/auth/verify-code", json={"email": "+23051234567", "code": sent_codes[-1]})
    assert res.status_code == 200 and client.get("/api/auth/me").json()["username"] == "asha_k"


def test_phone_only_login_sends_the_code_on_whatsapp(client, monkeypatch):  # no email -> WhatsApp (faked)
    sent = []
    monkeypatch.setattr(routes.auth, "send_otp_whatsapp", lambda phone, code: sent.append((phone, code)))
    monkeypatch.setattr(routes.auth, "send_otp_email", lambda email, code: pytest.fail("no email for this account"))
    client.post(REGISTER, json=phone_only())
    res = client.post("/api/auth/login", json={"email": "5123 4567", "password": PASSWORD})
    assert res.status_code == 200 and res.json()["code"] == "CODE_SENT_WHATSAPP"
    assert sent[-1][0] == "+23051234567" and len(sent[-1][1]) == 6
    res = client.post("/api/auth/verify-code", json={"email": "+23051234567", "code": sent[-1][1]})
    assert res.status_code == 200 and client.get("/api/auth/me").status_code == 200  # logged in


def test_phone_only_resend_and_wrong_password(client, sent_codes):
    client.post(REGISTER, json=phone_only())
    res = client.post("/api/auth/login", json={"email": "51234567", "password": "Wrong!Pass1"})
    assert res.status_code == 401 and sent_codes == []  # wrong password is still checked first
    assert client.post("/api/auth/login", json={"email": "51234567", "password": PASSWORD}).status_code == 200
    age_codes(31)  # pretend the 30-second resend wait is over
    res = client.post("/api/auth/resend-code", json={"email": "51234567"})
    assert res.status_code == 200 and res.json()["code"] == "CODE_RESENT_WHATSAPP" and len(sent_codes) == 2


def test_phone_only_login_without_twilio_keys(client, monkeypatch):  # not set up -> friendly 503, no crash
    def not_set_up(phone, code):
        raise routes.auth.WhatsAppNotConfigured()
    monkeypatch.setattr(routes.auth, "send_otp_whatsapp", not_set_up)
    client.post(REGISTER, json=phone_only())
    res = client.post("/api/auth/login", json={"email": "51234567", "password": PASSWORD})
    assert res.status_code == 503 and res.json()["code"] == "PHONE_CODE_NOT_AVAILABLE"


def test_phone_only_login_when_whatsapp_fails(client, monkeypatch):  # e.g. the phone hasn't joined the sandbox
    def fails(phone, code):
        raise routes.auth.WhatsAppFailed()
    monkeypatch.setattr(routes.auth, "send_otp_whatsapp", fails)
    client.post(REGISTER, json=phone_only())
    res = client.post("/api/auth/login", json={"email": "51234567", "password": PASSWORD})
    assert res.status_code == 503 and res.json()["code"] == "WHATSAPP_FAILED"
    with database.open_db() as db:  # the unsent code was not kept
        from models import OtpCode
        assert db.query(OtpCode).count() == 0


def test_login_id_must_be_an_email_or_phone(client):
    res = client.post("/api/auth/login", json={"email": "hello", "password": PASSWORD})
    assert res.status_code == 422 and res.json()["code"] == "INVALID_EMAIL"
