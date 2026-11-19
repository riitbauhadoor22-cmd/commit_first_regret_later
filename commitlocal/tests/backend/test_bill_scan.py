# test_bill_scan.py — "📷 Scan bill": a bill photo → {amount, date, shop, category} for the Add expense form.
# Groq is ALWAYS faked (conftest.fake_groq: fake_groq["bill_reply"]). Nothing is saved, photos only, max 5 MB,
# the Insights guards (no key, daily limit, cooldown) apply, and a bad reply gives "Couldn't read this bill".
import base64

import database
from models import AiRequestLog, Expense
from services.ai_insights import AiUnavailable
from services.bill_scan import MAX_IMAGE_BYTES

SCAN = "/api/expenses/scan-bill"
JPEG = b"\xff\xd8\xff\xe0" + b"fake jpeg bytes" * 10


def photo(raw=JPEG, media="image/jpeg"):
    return {"image": f"data:{media};base64," + base64.b64encode(raw).decode()}


def test_scan_fills_the_form_and_saves_nothing(logged_in, fake_groq):
    res = logged_in.post(SCAN, json=photo())
    assert res.status_code == 200
    assert res.json() == {"amount": 245.5, "date": None, "shop": "Winners", "category": "Groceries"}
    sent = fake_groq["last_scan_body"]["messages"][0]["content"]
    assert sent[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")  # the photo went to Groq only
    with database.open_db() as db:
        assert db.query(Expense).count() == 0  # nothing saved until the user taps Save
        logs = db.query(AiRequestLog).all()
        assert [(row.month, row.outcome) for row in logs] == [("bill-scan", "ok")]  # no photo stored anywhere


def test_unknown_category_and_odd_date_are_dropped(logged_in, fake_groq):
    fake_groq["bill_reply"] = '{"amount": 99, "date": "1999-01-01", "shop": "  KFC  ", "category": "Pizza"}'
    assert logged_in.post(SCAN, json=photo()).json() == {"amount": 99, "date": None, "shop": "KFC", "category": None}


def test_unreadable_bill(logged_in, fake_groq, monkeypatch):
    monkeypatch.setenv("BILL_SCAN_COOLDOWN_SECONDS", "0")
    for reply in ('{"amount": null}', "not json", '{"amount": -5}', AiUnavailable("AI_TIMEOUT")):
        fake_groq["bill_reply"] = reply
        res = logged_in.post(SCAN, json=photo())
        assert res.status_code == 502 and res.json()["code"] == "BILL_UNREADABLE"


def test_images_only(logged_in, fake_groq, monkeypatch):
    monkeypatch.setenv("BILL_SCAN_COOLDOWN_SECONDS", "0")
    for body in (photo(b"hello", "text/plain"), photo(b"\x89PNG\r\n\x1a\n...", "image/jpeg"),  # label ≠ bytes
                 {"image": "data:image/jpeg;base64,***"}, {"image": "https://example.com/bill.jpg"}):
        res = logged_in.post(SCAN, json=body)
        assert res.status_code == 400 and res.json()["code"] == "BILL_IMAGE_TYPE"
    assert logged_in.post(SCAN, json=photo(b"\x89PNG\r\n\x1a\n" + b"x" * 50, "image/png")).status_code == 200
    assert fake_groq.get("scan_calls") == 1  # bad files never reach Groq


def test_max_5_mb(logged_in, fake_groq):
    res = logged_in.post(SCAN, json=photo(JPEG + b"x" * MAX_IMAGE_BYTES))
    assert res.status_code == 400 and res.json()["code"] == "BILL_IMAGE_TOO_BIG"


def test_no_key_gives_a_friendly_message(logged_in, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    res = logged_in.post(SCAN, json=photo())
    assert res.status_code == 503 and res.json()["code"] == "BILL_SCAN_UNAVAILABLE"


def test_daily_limit_and_cooldown(logged_in, monkeypatch):
    monkeypatch.setenv("BILL_SCAN_COOLDOWN_SECONDS", "60")
    assert logged_in.post(SCAN, json=photo()).status_code == 200
    res = logged_in.post(SCAN, json=photo())
    assert res.status_code == 429 and res.json()["code"] == "BILL_SCAN_WAIT"
    monkeypatch.setenv("BILL_SCAN_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("BILL_SCAN_DAILY_LIMIT", "1")
    res = logged_in.post(SCAN, json=photo())
    assert res.status_code == 429 and res.json()["code"] == "BILL_SCAN_LIMIT"


def test_scans_dont_use_up_insights(logged_in, monkeypatch):
    from routes.insights import get_usage
    from services.ai_insights import get_settings
    assert logged_in.post(SCAN, json=photo()).status_code == 200
    with database.open_db() as db:
        user_id = db.query(AiRequestLog).first().user_id
        assert get_usage(db, user_id, get_settings())["used_today"] == 0
        assert get_usage(db, user_id, get_settings(), scans=True)["used_today"] == 1


def test_needs_login(client):
    assert client.post(SCAN, json=photo()).status_code == 401
