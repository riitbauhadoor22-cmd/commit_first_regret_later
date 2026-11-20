# test_auth.py — register, log in, /api/auth/me, where the code goes, the hourly code cap,
# demo mode, and sending (always faked: no real email is ever sent).
import smtplib

import httpx
import pytest
from sqlalchemy import select

import database
import email_sender
import routes.auth
from conftest import PASSWORD, age_codes, log_in, register
from models import User

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


@pytest.fixture
def brevo(monkeypatch):
    """Turns Brevo on and fakes its HTTP call (the real API is never called). Returns the list of sent requests."""
    monkeypatch.setenv("BREVO_API_KEY", "fake-brevo-key")
    monkeypatch.setenv("EMAIL_FROM", "codes@pennyworth.test")
    monkeypatch.setenv("EMAIL_FROM_NAME", "")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(201, json={"messageId": "x"})
    monkeypatch.setattr(email_sender.httpx, "post", fake_post)
    return calls


def test_brevo_used_when_key_is_set(brevo, no_real_smtp):
    email_sender.send_otp_email("asha@example.com", "123456")
    assert len(brevo) == 1
    call = brevo[0]
    assert call["url"] == "https://api.brevo.com/v3/smtp/email" and call["headers"]["api-key"] == "fake-brevo-key"
    assert call["timeout"] <= 10
    assert call["json"]["sender"] == {"email": "codes@pennyworth.test", "name": "Pennyworth"}
    assert call["json"]["to"] == [{"email": "asha@example.com"}]
    assert call["json"]["subject"] == "Your login code: 123456" and "123456" in call["json"]["textContent"]


def test_gmail_used_when_brevo_key_is_empty(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setattr(email_sender.httpx, "post", lambda *a, **k: pytest.fail("Brevo must not be called"))
    sent = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            sent.append(host)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def login(self, user, password):
            assert password == "abcdefghijklmnop"
        def send_message(self, message):
            sent.append(message["Subject"])
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    email_sender.send_otp_email("asha@example.com", "123456")
    assert sent == ["smtp.gmail.com", "Your login code: 123456"]


@pytest.mark.parametrize("problem", ["error", "timeout"])
def test_brevo_failure_gives_friendly_503(client, brevo, no_real_smtp, monkeypatch, capsys, problem):
    def failing_post(url, json, headers, timeout):
        if problem == "timeout":
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(401, json={"message": "Key not found"})
    monkeypatch.setattr(email_sender.httpx, "post", failing_post)
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 503 and res.json()["code"] == "EMAIL_FAILED"
    assert res.json()["detail"] == "We couldn't send the email right now. Please try again in a minute."
    assert "fake-brevo-key" not in capsys.readouterr().out  # the API key is never logged


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


# ===== USERNAME AT REGISTRATION =====
def saved_username(email="asha@example.com"):
    with database.open_db() as db:
        return db.scalar(select(User.username).where(User.email == email))


def test_register_username_is_lowercase(client):  # saved trimmed + lowercase
    assert client.post(REGISTER, json=form(username="  Asha_K  ")).status_code == 201
    assert saved_username() == "asha_k"


def test_register_ignores_a_phone_number(client):  # phone numbers are no longer taken: an old client's is ignored
    assert client.post(REGISTER, json=form(phone="5123 4567")).status_code == 201


@pytest.mark.parametrize("username", ["", "ab", "a" * 31, "asha k", "asha@k", "ásha", "   "])
def test_register_invalid_username(client, username):  # 3–30 of letters, digits . _ - only, else 422 INVALID_USERNAME
    res = client.post(REGISTER, json=form(username=username))
    assert res.status_code == 422 and res.json()["code"] == "INVALID_USERNAME"


def test_register_duplicate_username_any_case(client):  # same username (other case) -> 409 USERNAME_TAKEN
    assert client.post(REGISTER, json=form(username="Asha_K")).status_code == 201
    res = client.post(REGISTER, json=form(email="other@example.com", username="ASHA_k"))
    assert res.status_code == 409 and res.json()["code"] == "USERNAME_TAKEN"


@pytest.mark.parametrize("email", [None, "", "  "])
def test_register_needs_an_email(client, email):  # the email is how the user logs in -> 422
    assert client.post(REGISTER, json=form(email=email)).status_code == 422


# ===== WHERE THE CODE GOES =====
def test_code_is_emailed_with_masked_address(client, sent_codes):
    register(client)
    body = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).json()
    assert sent_codes.where == [("email", "asha@example.com")]
    assert body["code"] == "CODE_SENT" and body["sent_to"] == "a•••@example.com" and "channel" not in body


def test_wrong_password_reveals_no_address(client, sent_codes):
    register(client)
    body = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "Wrong!Pass1"}).json()
    assert "sent_to" not in body and sent_codes == []


def test_email_failure_saves_nothing(client, monkeypatch):
    def fail(email, code):
        raise smtplib.SMTPException("down")
    monkeypatch.setattr(routes.auth, "send_otp_email", fail)
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 503 and res.json()["code"] == "EMAIL_FAILED"
    with database.open_db() as db:  # the unsent code was not kept
        from models import OtpCode
        assert db.query(OtpCode).count() == 0


# ===== CODES PER HOUR =====
def test_sixth_code_in_an_hour_is_refused(client, sent_codes):
    register(client)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 200
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 429 and res.json()["code"] == "TOO_MANY_CODES" and len(sent_codes) == 5
    age_codes(31)
    res = client.post("/api/auth/resend-code", json={"email": "asha@example.com"})
    assert res.status_code == 429 and res.json()["code"] == "TOO_MANY_CODES"  # resend counts too
    age_codes(60 * 60)  # an hour later: allowed again
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 200


# ===== DEMO MODE =====
def test_no_demo_code_by_default(client, sent_codes):
    register(client)
    login = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).json()
    age_codes(31)
    resend = client.post("/api/auth/resend-code", json={"email": "asha@example.com"}).json()
    assert "demo_code" not in login and "demo_code" not in resend


@pytest.mark.parametrize("value", ["false", "", "True", "yes"])
def test_demo_mode_needs_exactly_true(client, sent_codes, monkeypatch, value):
    monkeypatch.setenv("DEMO_SHOW_OTP", value)
    register(client)
    assert "demo_code" not in client.post("/api/auth/login", json={"email": "asha@example.com",
                                                                   "password": PASSWORD}).json()


def test_demo_mode_shows_the_sent_code_after_the_password(client, sent_codes, monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_OTP", "true")
    register(client)
    body = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).json()
    assert body["demo_code"] == sent_codes[-1]
    age_codes(31)
    resend = client.post("/api/auth/resend-code", json={"email": "asha@example.com"}).json()  # no password: no code
    assert resend["code"] == "CODE_RESENT" and "demo_code" not in resend


def test_demo_mode_when_email_fails_saves_nothing(client, monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_OTP", "true")

    def fail(email, code):
        raise smtplib.SMTPException("down")
    monkeypatch.setattr(routes.auth, "send_otp_email", fail)
    register(client)
    res = client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert res.status_code == 503 and "demo_code" not in res.json()
    with database.open_db() as db:
        from models import OtpCode
        assert db.query(OtpCode).count() == 0


# ===== LOCKED ACCOUNT: SAME REPLY ALWAYS =====
def lock(client, login_id):
    for _ in range(3):
        client.post("/api/auth/login", json={"email": login_id, "password": "Wrong!Pass1"})


def test_send_login_code_reply_is_the_same_for_every_account(client, sent_codes, monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_OTP", "true")  # even in demo mode nothing extra is shown here
    register(client)  # not locked
    client.post(REGISTER, json=form(username="locked_one", email="locked@example.com"))
    lock(client, "locked@example.com")
    replies = [client.post("/api/auth/send-login-code", json={"email": login_id})
               for login_id in ["nobody@example.com", "asha@example.com", "locked@example.com"]]
    assert {res.status_code for res in replies} == {200}
    assert len({res.text for res in replies}) == 1  # identical replies
    assert set(replies[0].json()) == {"message", "code"}
    assert sent_codes.where == [("email", "locked@example.com")]  # only the locked email account got a code


def test_send_login_code_respects_the_hourly_cap(client, sent_codes):
    register(client)
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    age_codes(31)
    lock(client, "asha@example.com")
    res = client.post("/api/auth/send-login-code", json={"email": "asha@example.com"})
    assert res.status_code == 200 and res.json()["code"] == "LOCKED_CODE_SENT" and len(sent_codes) == 5  # not sent


def test_login_id_must_be_an_email(client):
    res = client.post("/api/auth/login", json={"email": "hello", "password": PASSWORD})
    assert res.status_code == 422 and res.json()["code"] == "INVALID_EMAIL"
