# test_otp.py — tests for the login code: expiry (410), "Resend OTP", and the 30-second resend cooldown.
from conftest import PASSWORD, age_codes, register

EMAIL = "asha@example.com"


def start_login(client):
    res = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["expires_in"] == 300
    return res


# ===== EXPIRY =====
def test_expired_code_returns_expired_error(client, sent_codes):
    register(client)
    start_login(client)
    age_codes(5 * 60 + 1)  # just over 5 minutes later
    res = client.post("/api/auth/verify-code", json={"email": EMAIL, "code": sent_codes[-1]})
    assert res.status_code == 410
    assert "expired" in res.json()["detail"]


def test_valid_code_logs_in(client, sent_codes):
    register(client)
    start_login(client)
    res = client.post("/api/auth/verify-code", json={"email": EMAIL, "code": sent_codes[-1]})
    assert res.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


# ===== RESEND + COOLDOWN =====
def test_resend_blocked_during_cooldown(client, sent_codes):
    register(client)
    start_login(client)
    res = client.post("/api/auth/resend-code", json={"email": EMAIL})
    assert res.status_code == 429
    assert len(sent_codes) == 1  # no second email


def test_resend_after_cooldown_sends_new_code_and_old_one_stops_working(client, sent_codes):
    register(client)
    start_login(client)
    old_code = sent_codes[-1]
    age_codes(31)
    res = client.post("/api/auth/resend-code", json={"email": EMAIL})
    assert res.status_code == 200
    assert len(sent_codes) == 2
    new_code = sent_codes[-1]
    if old_code != new_code:  # (1 in a million chance they match)
        bad = client.post("/api/auth/verify-code", json={"email": EMAIL, "code": old_code})
        assert bad.status_code == 400
    ok = client.post("/api/auth/verify-code", json={"email": EMAIL, "code": new_code})
    assert ok.status_code == 200


def test_resend_after_expiry_works(client, sent_codes):
    register(client)
    start_login(client)
    age_codes(6 * 60)
    assert client.post("/api/auth/resend-code", json={"email": EMAIL}).status_code == 200
    res = client.post("/api/auth/verify-code", json={"email": EMAIL, "code": sent_codes[-1]})
    assert res.status_code == 200


def test_resend_cooldown_restarts_after_resend(client, sent_codes):
    register(client)
    start_login(client)
    age_codes(31)
    assert client.post("/api/auth/resend-code", json={"email": EMAIL}).status_code == 200
    assert client.post("/api/auth/resend-code", json={"email": EMAIL}).status_code == 429


def test_resend_without_login_step_is_refused(client, sent_codes):
    register(client)
    res = client.post("/api/auth/resend-code", json={"email": EMAIL})
    assert res.status_code == 400
    assert sent_codes == []


def test_resend_for_unknown_email_is_refused(client, sent_codes):
    res = client.post("/api/auth/resend-code", json={"email": "nobody@example.com"})
    assert res.status_code == 400
    assert sent_codes == []
