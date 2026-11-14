# whatsapp_sender.py — sends the 6-digit login code on WhatsApp through the Meta WhatsApp Cloud API
# (graph.facebook.com), using an approved AUTHENTICATION template with a "copy code" button.
# Settings live only in backend/.env (see README.md "WhatsApp login codes" for the step-by-step setup):
#   WHATSAPP_ENABLED=true, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TEMPLATE_NAME,
#   WHATSAPP_TEMPLATE_LANG (default en_US), WHATSAPP_API_VERSION (optional, default below).
# Called only from deliver_login_code() in routes/auth.py. The code and the token are never written to the logs.
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)

DEFAULT_API_VERSION = "v27.0"  # Graph API version used in Meta's authentication-template docs (Nov 2026)
DEFAULT_TEMPLATE_LANG = "en_US"
GRAPH_URL = "https://graph.facebook.com/{version}/{phone_number_id}/messages"
TIMEOUT_SECONDS = 10


class WhatsAppNotConfigured(Exception):
    """WHATSAPP_ENABLED is not "true", or a required WhatsApp value is missing in backend/.env."""


class WhatsAppFailed(Exception):
    """Meta couldn't send the message (network, expired token, number not in the test list, template not approved...)."""


def read_setting(name, default=""):
    return (os.getenv(name) or "").strip() or default


def get_whatsapp_settings():
    """The values from backend/.env as a dict. Turned off or anything missing → WhatsAppNotConfigured."""
    if read_setting("WHATSAPP_ENABLED").lower() != "true":
        raise WhatsAppNotConfigured()
    settings = {
        "token": read_setting("WHATSAPP_ACCESS_TOKEN"),
        "phone_number_id": read_setting("WHATSAPP_PHONE_NUMBER_ID"),
        "template": read_setting("WHATSAPP_TEMPLATE_NAME"),
        "lang": read_setting("WHATSAPP_TEMPLATE_LANG", DEFAULT_TEMPLATE_LANG),
        "version": read_setting("WHATSAPP_API_VERSION", DEFAULT_API_VERSION),
    }
    if not settings["token"] or not settings["phone_number_id"] or not settings["template"]:
        raise WhatsAppNotConfigured()
    return settings


def build_template_message(to_phone, code, template, lang):
    """The JSON Meta expects for an authentication template: the code goes in the body AND the copy-code button."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone.lstrip("+"),  # "+23051234567" → "23051234567"
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]},
            ],
        },
    }


def read_meta_error(res):
    """Meta's error number + message (e.g. 131030 "Recipient phone number not in allowed list"), for the server log."""
    try:
        error = res.json().get("error") or {}
    except (ValueError, AttributeError):
        return None, None
    return error.get("code"), error.get("message")


def send_otp_whatsapp(to_phone, code):
    """Sends the login code to a phone number (+230...) on WhatsApp. One try, never retried here."""
    settings = get_whatsapp_settings()
    url = GRAPH_URL.format(version=settings["version"], phone_number_id=settings["phone_number_id"])
    body = build_template_message(to_phone, code, settings["template"], settings["lang"])
    try:
        res = httpx.post(url, json=body, timeout=TIMEOUT_SECONDS,
                         headers={"Authorization": "Bearer " + settings["token"]})
    except httpx.HTTPError as error:
        log.warning("WhatsApp code not sent: %s", type(error).__name__)
        raise WhatsAppFailed()
    if res.status_code >= 300:
        meta_code, meta_message = read_meta_error(res)  # Meta's own words, never the code or the token
        log.warning("WhatsApp code not sent: Meta HTTP %s, error %s: %s", res.status_code, meta_code, meta_message)
        raise WhatsAppFailed()
