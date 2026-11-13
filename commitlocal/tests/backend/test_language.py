# test_language.py — PUT /api/auth/language saves the chosen language on the account; GET /api/auth/me returns it.
import pytest
from conftest import log_in


# ===== SAVE / READ =====
def test_language_is_null_until_chosen_then_saved(logged_in):
    assert logged_in.get("/api/auth/me").json()["language"] is None
    for code in ("fr", "mfe", "en"):
        res = logged_in.put("/api/auth/language", json={"language": code})
        assert res.status_code == 200 and res.json() == {"language": code}
        assert logged_in.get("/api/auth/me").json()["language"] == code


@pytest.mark.parametrize("bad", ["de", "", "FR", None, 5, "english"])
def test_invalid_language_rejected(logged_in, bad):
    res = logged_in.put("/api/auth/language", json={"language": bad})
    assert res.status_code == 422
    assert res.json()["code"] == "INVALID_LANGUAGE"
    assert logged_in.get("/api/auth/me").json()["language"] is None  # nothing saved


def test_missing_language_rejected(logged_in):
    assert logged_in.put("/api/auth/language", json={}).json()["code"] == "INVALID_LANGUAGE"


def test_needs_login(client):
    res = client.put("/api/auth/language", json={"language": "fr"})
    assert res.status_code == 401 and res.json()["code"] == "NOT_LOGGED_IN"


# ===== ONE USER ONLY =====
def test_choice_does_not_affect_other_user(new_client, sent_codes):
    user_a = log_in(new_client(), sent_codes, "a@example.com")
    user_b = log_in(new_client(), sent_codes, "b@example.com")
    assert user_a.put("/api/auth/language", json={"language": "mfe"}).status_code == 200
    assert user_b.get("/api/auth/me").json()["language"] is None
    user_b.put("/api/auth/language", json={"language": "fr"})
    assert user_a.get("/api/auth/me").json()["language"] == "mfe"
