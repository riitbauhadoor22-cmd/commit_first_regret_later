# test_whatsapp_sender.py — the WhatsApp login-code sender (Meta WhatsApp Cloud API). Meta is ALWAYS faked here:
# httpx.post is replaced, so no real message is ever sent and no real token is needed.
import logging

import httpx
import pytest

import whatsapp_sender
from whatsapp_sender import WhatsAppFailed, WhatsAppNotConfigured, send_otp_whatsapp

SETTINGS = {"WHATSAPP_ENABLED": "true", "WHATSAPP_ACCESS_TOKEN": "secret-token", "WHATSAPP_PHONE_NUMBER_ID": "1055123",
            "WHATSAPP_TEMPLATE_NAME": "login_code", "WHATSAPP_TEMPLATE_LANG": "en_US", "WHATSAPP_API_VERSION": ""}


@pytest.fixture
def meta_settings(monkeypatch):
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def fake_post(monkeypatch):
    """Records what would be sent to Meta and answers with `reply` (a Response or an exception)."""
    state = {"reply": httpx.Response(200, json={"messages": [{"id": "wamid.1"}]}), "calls": []}

    def post(url, **kwargs):
        state["calls"].append({"url": url, **kwargs})
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(whatsapp_sender.httpx, "post", post)
    return state


# ===== THE REQUEST =====
def test_sends_the_authentication_template(meta_settings, fake_post):
    send_otp_whatsapp("+23057001234", "123456")
    call = fake_post["calls"][0]
    assert call["url"] == "https://graph.facebook.com/v27.0/1055123/messages"  # default version
    assert call["headers"]["Authorization"] == "Bearer secret-token"
    assert call["timeout"] == 10
    body = call["json"]
    assert body["messaging_product"] == "whatsapp" and body["type"] == "template"
    assert body["to"] == "23057001234"  # E.164 digits without "+"
    template = body["template"]
    assert template["name"] == "login_code" and template["language"] == {"code": "en_US"}
    body_part, button = template["components"]
    assert body_part == {"type": "body", "parameters": [{"type": "text", "text": "123456"}]}
    assert button == {"type": "button", "sub_type": "url", "index": "0",
                      "parameters": [{"type": "text", "text": "123456"}]}  # the copy-code button


def test_version_and_language_can_be_changed(meta_settings, fake_post, monkeypatch):
    monkeypatch.setenv("WHATSAPP_API_VERSION", "v26.0")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "fr")
    send_otp_whatsapp("+23057001234", "123456")
    call = fake_post["calls"][0]
    assert call["url"] == "https://graph.facebook.com/v26.0/1055123/messages"
    assert call["json"]["template"]["language"] == {"code": "fr"}


def test_language_defaults_to_en_us(meta_settings, fake_post, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "")
    send_otp_whatsapp("+23057001234", "123456")
    assert fake_post["calls"][0]["json"]["template"]["language"] == {"code": "en_US"}


# ===== NOT SET UP =====
@pytest.mark.parametrize("enabled", ["false", "", "yes", "1"])
def test_not_enabled_means_not_configured(meta_settings, fake_post, monkeypatch, enabled):  # only "true" turns it on
    monkeypatch.setenv("WHATSAPP_ENABLED", enabled)
    with pytest.raises(WhatsAppNotConfigured):
        send_otp_whatsapp("+23057001234", "123456")
    assert fake_post["calls"] == []  # nothing tried


@pytest.mark.parametrize("missing", ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_TEMPLATE_NAME"])
def test_missing_value_means_not_configured(meta_settings, fake_post, monkeypatch, missing):
    monkeypatch.setenv(missing, "  ")
    with pytest.raises(WhatsAppNotConfigured):
        send_otp_whatsapp("+23057001234", "123456")
    assert fake_post["calls"] == []


# ===== META PROBLEMS =====
@pytest.mark.parametrize("reply", [
    httpx.Response(400, json={"error": {"code": 131030, "message": "Recipient phone number not in allowed list"}}),
    httpx.Response(401, json={"error": {"code": 190, "message": "Error validating access token"}}),
    httpx.Response(500, text="oops"), httpx.ReadTimeout("slow"), httpx.ConnectError("offline")])
def test_meta_problems_become_one_error(meta_settings, fake_post, reply, caplog):
    caplog.set_level(logging.WARNING)
    fake_post["reply"] = reply
    with pytest.raises(WhatsAppFailed):
        send_otp_whatsapp("+23057001234", "654321")
    assert len(fake_post["calls"]) == 1  # one try, no retries
    assert "654321" not in caplog.text and "secret-token" not in caplog.text  # never logged
    assert "WhatsApp code not sent" in caplog.text


def test_meta_error_details_are_logged(meta_settings, fake_post, caplog):  # helps the server owner fix the setup
    caplog.set_level(logging.WARNING)
    fake_post["reply"] = httpx.Response(404, json={"error": {"code": 132001, "message": "Template name does not exist"}})
    with pytest.raises(WhatsAppFailed):
        send_otp_whatsapp("+23057001234", "654321")
    assert "404" in caplog.text and "132001" in caplog.text and "Template name does not exist" in caplog.text
