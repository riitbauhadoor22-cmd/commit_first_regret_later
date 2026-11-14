# whatsapp_sender.py — sends the 6-digit login code by WhatsApp to accounts that registered with a phone number only.
# It uses Twilio's WhatsApp SANDBOX (free on a Twilio trial account: fine for a demo, not for real users):
#   1. twilio.com/try-twilio → Console → Messaging → Try it out → Send a WhatsApp message (shows the sandbox number + code)
#   2. every tester sends "join <code>" to the sandbox number on WhatsApp once (it lasts 3 days)
#   3. backend/.env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM (the sandbox number, e.g. +14155238886)
# The keys live only in backend/.env. The code and the token are never written to the logs.
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)

TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
TIMEOUT_SECONDS = 10


class WhatsAppNotConfigured(Exception):
    """The Twilio keys are missing in backend/.env."""


class WhatsAppFailed(Exception):
    """Twilio couldn't send the message (network, wrong keys, the phone hasn't joined the sandbox, ...)."""


def get_twilio_settings():
    sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
    token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
    sender = (os.getenv("TWILIO_WHATSAPP_FROM") or "").strip()
    if not sid or not token or not sender:
        raise WhatsAppNotConfigured()
    return sid, token, sender


def whatsapp_address(phone):
    """'+23057001234' -> 'whatsapp:+23057001234' (how Twilio names WhatsApp numbers)."""
    return "whatsapp:" + phone if not phone.startswith("whatsapp:") else phone


def build_message(code):
    return f"Your My Money login code is {code}. It expires in 5 minutes. If you didn't try to log in, ignore this."


def send_otp_whatsapp(to_phone, code):
    """Sends the login code to a phone number (+230...) on WhatsApp. One try, never retried here."""
    sid, token, sender = get_twilio_settings()
    try:
        res = httpx.post(TWILIO_URL.format(sid=sid), auth=(sid, token), timeout=TIMEOUT_SECONDS,
                         data={"From": whatsapp_address(sender), "To": whatsapp_address(to_phone),
                               "Body": build_message(code)})
    except httpx.HTTPError as error:
        log.warning("WhatsApp code not sent: %s", type(error).__name__)
        raise WhatsAppFailed()
    if res.status_code >= 400:
        # Twilio's error number helps (e.g. 63015 = this phone hasn't joined the sandbox); no code or token logged
        try:
            twilio_code = res.json().get("code")
        except ValueError:
            twilio_code = None
        log.warning("WhatsApp code not sent: Twilio HTTP %s, error %s", res.status_code, twilio_code)
        raise WhatsAppFailed()
