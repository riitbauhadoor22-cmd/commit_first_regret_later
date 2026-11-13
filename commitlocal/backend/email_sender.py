# email_sender.py — emails the 6-digit login code through Gmail, using the address + App Password in .env.
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def send_otp_email(to_email, code):
    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")  # Google shows it with spaces
    if not sender or not app_password:
        raise RuntimeError("Gmail is not set up: fill GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env")

    message = EmailMessage()
    message["Subject"] = f"Your login code: {code}"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"Your login code is {code}\n\n"
        "It expires in 5 minutes. If you didn't try to log in, you can ignore this email."
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
