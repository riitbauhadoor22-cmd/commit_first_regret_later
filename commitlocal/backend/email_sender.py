# email_sender.py — emails the 6-digit login code. Brevo HTTP API when BREVO_API_KEY is set (Render's free plan
# blocks SMTP ports), otherwise Gmail SMTP with the address + App Password in .env (local development).
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT_SECONDS = 10


def email_text(code):
    """The subject and body of the login code email (same for Brevo and Gmail)."""
    subject = f"Your login code: {code}"
    body = (f"Your login code is {code}\n\n"
            "It expires in 5 minutes. If you didn't try to log in, you can ignore this email.")
    return subject, body


def send_otp_email(to_email, code):
    if os.getenv("BREVO_API_KEY", "").strip():
        send_with_brevo(to_email, code)
    else:
        send_with_gmail(to_email, code)


def send_with_brevo(to_email, code):
    """One try, no retries. Any problem raises, and the caller answers 503 EMAIL_FAILED.
    Errors never include the code or the API key (only the status number)."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "").strip()
    if not sender:
        raise RuntimeError("Brevo is not set up: fill EMAIL_FROM in backend/.env")
    subject, body = email_text(code)
    payload = {
        "sender": {"email": sender, "name": os.getenv("EMAIL_FROM_NAME", "").strip() or "Pennyworth"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    try:
        res = httpx.post(BREVO_URL, json=payload, timeout=BREVO_TIMEOUT_SECONDS,
                         headers={"api-key": api_key, "accept": "application/json"})
    except httpx.TimeoutException:
        raise RuntimeError("Brevo timed out") from None
    except httpx.HTTPError as error:
        raise RuntimeError(f"Brevo connection failed ({type(error).__name__})") from None
    if res.status_code >= 300:
        raise RuntimeError(f"Brevo replied {res.status_code}")


def send_with_gmail(to_email, code):
    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")  # Google shows it with spaces
    if not sender or not app_password:
        raise RuntimeError("Gmail is not set up: fill GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env")

    subject, body = email_text(code)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
