# test_rate_limit.py — the in-memory rate limiter (login / register / code routes), daily code caps,
# and the production settings (Secure cookie, HSTS, no /docs, /health, friendly 500, profile 409 on a race).
import pytest
from fastapi.testclient import TestClient

import config
import rate_limit
import routes.auth
from conftest import PASSWORD, log_in, register, username_for


# ===== FIXTURES / HELPERS =====
@pytest.fixture
def limiter_on():
    rate_limit.reset()
    rate_limit.enabled = True  # conftest turns it off for every other test


def client_from(ip):
    """A "browser" calling from this IP address."""
    import main
    return TestClient(main.app, client=(ip, 50000))


def assert_too_many(res):
    assert res.status_code == 429
    assert res.json()["code"] == "TOO_MANY_REQUESTS"
    assert int(res.headers["Retry-After"]) >= 1


def login(client, email="asha@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ===== LIMITER UNIT =====
def test_hit_blocks_after_limit_and_reset_clears(limiter_on):
    for _ in range(3):
        rate_limit.hit("k", 3, 60)
    with pytest.raises(Exception) as error:
        rate_limit.hit("k", 3, 60)
    assert error.value.code == "TOO_MANY_REQUESTS"
    rate_limit.reset()
    rate_limit.hit("k", 3, 60)  # allowed again


def test_disabled_limiter_never_blocks():
    for _ in range(50):
        rate_limit.hit("k", 1, 60)


# ===== ROUTES =====
def test_register_limited_per_ip(client, limiter_on, monkeypatch):
    monkeypatch.setattr(routes.auth, "REGISTER_PER_IP", (2, 3600))
    register(client, "a1@example.com")
    register(client, "a2@example.com")
    res = client.post("/api/auth/register", json={"username": username_for("a3@example.com"), "email": "a3@example.com",
                                                  "password": PASSWORD, "confirm_password": PASSWORD})
    assert_too_many(res)


def test_login_limited_per_ip(client, limiter_on, monkeypatch):
    monkeypatch.setattr(routes.auth, "LOGIN_PER_IP", (2, 900))
    assert login(client, "nobody1@example.com").status_code == 401
    assert login(client, "nobody2@example.com").status_code == 401
    assert_too_many(login(client, "nobody3@example.com"))


def test_login_limited_per_account_from_any_ip(client, limiter_on, monkeypatch):
    monkeypatch.setattr(routes.auth, "LOGIN_PER_ACCOUNT", (2, 900))
    assert login(client_from("1.1.1.1"), "nobody@example.com").status_code == 401
    assert login(client_from("2.2.2.2"), "nobody@example.com").status_code == 401
    assert_too_many(login(client_from("3.3.3.3"), "nobody@example.com"))


def test_wrong_codes_counted_per_ip(client, sent_codes, limiter_on, monkeypatch):
    """M1: one attacker IP is stopped before it can use up the victim's hourly guesses."""
    monkeypatch.setattr(routes.auth, "WRONG_CODES_PER_IP", (3, 3600))
    register(client)
    assert login(client).status_code == 200
    real = sent_codes[-1]
    wrong = "000000" if real != "000000" else "111111"
    attacker = client_from("6.6.6.6")
    for _ in range(3):
        assert attacker.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": wrong}).status_code == 400
    assert_too_many(attacker.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": real}))
    victim = client_from("7.7.7.7")
    assert victim.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": real}).status_code == 200


def test_daily_code_cap_per_account(client, sent_codes, monkeypatch):
    """M2: works even with the in-memory limiter off (counted in the database)."""
    monkeypatch.setattr(routes.auth, "CODES_PER_DAY_PER_ACCOUNT", 2)
    register(client)
    assert login(client).status_code == 200
    assert login(client).status_code == 200
    assert_too_many(login(client))
    assert len(sent_codes) == 2


def test_daily_code_cap_per_ip(client, sent_codes, limiter_on, monkeypatch):
    monkeypatch.setattr(routes.auth, "CODES_PER_DAY_PER_IP", (1, 86400))
    register(client, "a@example.com")
    register(client, "b@example.com")
    assert login(client, "a@example.com").status_code == 200
    assert_too_many(login(client, "b@example.com"))
    assert len(sent_codes) == 1


def test_resend_and_locked_code_limited_per_ip(client, limiter_on, monkeypatch):
    monkeypatch.setattr(routes.auth, "RESEND_PER_IP", (2, 900))
    body = {"email": "nobody@example.com"}
    assert client.post("/api/auth/send-login-code", json=body).status_code == 200
    assert client.post("/api/auth/resend-code", json=body).status_code == 400
    assert_too_many(client.post("/api/auth/send-login-code", json=body))


# ===== PRODUCTION SETTINGS =====
def test_cookie_secure_only_in_production(client, sent_codes, monkeypatch):
    register(client)
    assert login(client).status_code == 200
    res = client.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": sent_codes[-1]})
    assert "secure" not in res.headers["set-cookie"].lower()  # development on http://localhost keeps working
    assert login(client).status_code == 200
    monkeypatch.setenv("APP_ENV", "production")
    res = client.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": sent_codes[-1]})
    cookie = res.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_hsts_and_referrer_policy(client, monkeypatch):
    res = client.get("/health")
    assert res.json() == {"status": "ok"}
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in res.headers
    monkeypatch.setenv("APP_ENV", "production")
    assert client.get("/health").headers["Strict-Transport-Security"] == "max-age=31536000"


def test_docs_only_in_development(client, monkeypatch):
    assert client.get("/docs").status_code == 200
    assert config.docs_settings() == {}
    monkeypatch.delenv("APP_ENV")
    monkeypatch.setenv("ENV", "production")  # ENV works when APP_ENV is not set
    assert config.docs_settings() == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_unexpected_error_is_friendly(new_client, monkeypatch):
    import main
    def boom(request):
        raise RuntimeError("secret stack detail")
    monkeypatch.setattr(routes.auth, "get_current_user", boom)
    res = TestClient(main.app, raise_server_exceptions=False).get("/api/auth/me")
    assert res.status_code == 500
    assert res.json()["code"] == "SERVER_ERROR"
    assert "secret stack detail" not in res.text


def test_profile_username_race_gives_409(new_client, sent_codes, monkeypatch):
    """L5: the UNIQUE rule in the database catches what the "is it taken?" check missed."""
    import routes.profile
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    log_in(new_client(), sent_codes, "ben@example.com")
    monkeypatch.setattr(routes.profile, "find_user_by_username", lambda db, name: None)  # the check "misses" Ben
    res = asha.put("/api/profile/username", json={"username": username_for("ben@example.com")})
    assert res.status_code == 409
    assert res.json()["code"] == "USERNAME_TAKEN"
