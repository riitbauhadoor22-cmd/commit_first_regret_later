# test_whatsapp_sender.py — the WhatsApp login-code sender (Twilio sandbox). Twilio is ALWAYS faked here:
# httpx.post is replaced, so no real message is ever sent and no keys are needed.
import httpx
import pytest

import whatsapp_sender
from whatsapp_sender import WhatsAppFailed, WhatsAppNotConfigured, send_otp_whatsapp

KEYS = {"TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "secret-token", "TWILIO_WHATSAPP_FROM": "+14155238886"}


@pytest.fixture
def twilio_keys(monkeypatch):
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def fake_post(monkeypatch):
    """Records what would be sent to Twilio and answers with `reply` (a Response or an exception)."""
    state = {"reply": httpx.Response(201, json={"sid": "SM1"}), "calls": []}

    def post(url, **kwargs):
        state["calls"].append({"url": url, **kwargs})
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(whatsapp_sender.httpx, "post", post)
    return state


def test_sends_the_code_on_whatsapp(twilio_keys, fake_post):
    send_otp_whatsapp("+23057001234", "123456")
    call = fake_post["calls"][0]
    assert call["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
    assert call["auth"] == ("ACtest", "secret-token")
    assert call["data"]["To"] == "whatsapp:+23057001234"
    assert call["data"]["From"] == "whatsapp:+14155238886"
    assert "123456" in call["data"]["Body"] and call["timeout"] == 10


def test_missing_keys_means_not_configured(monkeypatch, fake_post):
    for name in KEYS:
        monkeypatch.setenv(name, "")
    with pytest.raises(WhatsAppNotConfigured):
        send_otp_whatsapp("+23057001234", "123456")
    assert fake_post["calls"] == []  # nothing tried


@pytest.mark.parametrize("reply", [httpx.Response(400, json={"code": 63015, "message": "not joined"}),
                                   httpx.Response(401, json={"code": 20003}), httpx.Response(500, text="oops"),
                                   httpx.ConnectTimeout("slow"), httpx.ConnectError("offline")])
def test_twilio_problems_become_one_error(twilio_keys, fake_post, reply, caplog):
    fake_post["reply"] = reply
    with pytest.raises(WhatsAppFailed):
        send_otp_whatsapp("+23057001234", "654321")
    assert len(fake_post["calls"]) == 1  # one try, no retries
    assert "654321" not in caplog.text and "secret-token" not in caplog.text  # never logged


def test_number_already_prefixed_is_not_doubled(twilio_keys, fake_post):
    send_otp_whatsapp("whatsapp:+23057001234", "111111")
    assert fake_post["calls"][0]["data"]["To"] == "whatsapp:+23057001234"
