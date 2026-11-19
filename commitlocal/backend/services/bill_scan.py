# services/bill_scan.py — "📷 Scan bill": reads a photo of a bill with a Groq vision model and returns
# {amount, date, shop, category} to FILL IN the Add expense form (nothing is saved here; the user taps Save).
# The photo is only sent to Groq for this one request: it is never stored and never logged (only status codes are).
# Settings (backend/.env): GROQ_API_KEY (shared with Financial insights), GROQ_VISION_MODEL (default below; Groq's
# vision models are "preview" models, check console.groq.com/docs/vision), BILL_SCAN_DAILY_LIMIT,
# BILL_SCAN_COOLDOWN_SECONDS. The daily limit / cooldown / no-key checks reuse the Insights guards (routes/expenses).
import base64
import binascii
import datetime
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from categories import CATEGORIES
from services.ai_insights import GROQ_URL, AiUnavailable, read_retry_after, read_whole_number

log = logging.getLogger("bill_scan")

DEFAULT_VISION_MODEL = "qwen/qwen3.8-27b"  # Groq preview vision model with JSON mode (checked Nov 2026)
MAX_IMAGE_BYTES = 5 * 1024 * 1024          # 5 MB after decoding
IMAGE_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}
DATA_URL = re.compile(r"^data:(image/[a-z]+);base64,([A-Za-z0-9+/=\s]+)$")
SCAN_LOG_MONTH = "bill-scan"  # AiRequestLog.month for scans, so they don't use up the Insights limit


@dataclass
class ScanSettings:
    api_key: str
    model: str
    daily_limit: int
    cooldown_seconds: int
    timeout_seconds: int


def get_scan_settings():
    return ScanSettings(
        api_key=(os.getenv("GROQ_API_KEY") or "").strip(),
        model=(os.getenv("GROQ_VISION_MODEL") or "").strip() or DEFAULT_VISION_MODEL,
        daily_limit=read_whole_number("BILL_SCAN_DAILY_LIMIT", 10),
        cooldown_seconds=read_whole_number("BILL_SCAN_COOLDOWN_SECONDS", 10),
        timeout_seconds=read_whole_number("AI_TIMEOUT_SECONDS", 25),
    )


# ===== THE PHOTO =====
class ImageProblem(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def check_image(data_url):
    """'data:image/jpeg;base64,...' → (media type, base64 text). Images only (checked by their first bytes, not just
    the label), at most 5 MB. Raises ImageProblem BILL_IMAGE_TYPE / BILL_IMAGE_TOO_BIG."""
    match = DATA_URL.match(data_url or "")
    if not match or match.group(1) not in IMAGE_TYPES:
        raise ImageProblem("BILL_IMAGE_TYPE")
    text = re.sub(r"\s", "", match.group(2))
    if len(text) * 3 // 4 > MAX_IMAGE_BYTES + 3:
        raise ImageProblem("BILL_IMAGE_TOO_BIG")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ImageProblem("BILL_IMAGE_TYPE")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageProblem("BILL_IMAGE_TOO_BIG")
    if not raw.startswith(IMAGE_TYPES[match.group(1)]):
        raise ImageProblem("BILL_IMAGE_TYPE")
    return match.group(1), text


# ===== THE CALL =====
PROMPT = ("You read photos of shop bills / receipts from Mauritius (amounts in rupees, Rs). Reply with ONE JSON "
          "object only: {\"amount\": total paid as a number or null, \"date\": \"YYYY-MM-DD\" or null, "
          "\"shop\": shop name (short) or null, \"category\": one of " + json.dumps(list(CATEGORIES)) +
          " or null}. Use the final total, not a subtotal. If it is not a bill or you can't read it, "
          "reply {\"amount\": null, \"date\": null, \"shop\": null, \"category\": null}.")


def build_scan_body(media_type, base64_text, settings):
    return {"model": settings.model, "temperature": 0, "max_completion_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64_text}"}},
            ]}]}


def send_scan(body, settings):
    """Sends the photo to Groq and returns the reply text. Raises AiUnavailable on any problem.
    Only status codes are logged: never the photo, the reply or the key."""
    try:
        res = httpx.post(GROQ_URL, json=body, timeout=settings.timeout_seconds,
                         headers={"Authorization": "Bearer " + settings.api_key})
    except httpx.TimeoutException:
        raise AiUnavailable("AI_TIMEOUT")
    except httpx.HTTPError as error:
        log.warning("Bill scan request failed: %s", type(error).__name__)
        raise AiUnavailable("AI_FAILED")
    if res.status_code == 429:
        raise AiUnavailable("AI_RATE_LIMITED", read_retry_after(res.headers))
    if res.status_code >= 400:
        log.warning("Bill scan: Groq answered HTTP %s", res.status_code)
        raise AiUnavailable("AI_FAILED")
    try:
        return res.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AiUnavailable("AI_BAD_RESPONSE")


# ===== THE REPLY =====
class BillReply(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    date: Optional[datetime.date] = None
    shop: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = None

    @field_validator("category")
    @classmethod
    def known_category(cls, value):
        return value if value in CATEGORIES else None  # an unknown category is just not suggested

    @field_validator("date", mode="before")
    @classmethod
    def sensible_date(cls, value):
        try:
            day = datetime.date.fromisoformat(str(value)[:10]) if value else None
        except ValueError:
            return None
        return day if day and abs((day - datetime.date.today()).days) <= 366 else None  # misread years are dropped


def parse_bill(text):
    """The checked reply → {amount, date, shop, category}. No readable amount → AiUnavailable BILL_UNREADABLE."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        if isinstance(data.get("shop"), str):
            data["shop"] = data["shop"].strip()[:60] or None
        bill = BillReply.model_validate(data)
    except (ValueError, TypeError, ValidationError):
        raise AiUnavailable("BILL_UNREADABLE")
    if bill.amount is None:
        raise AiUnavailable("BILL_UNREADABLE")
    return {"amount": round(bill.amount, 2), "date": bill.date.isoformat() if bill.date else None,
            "shop": bill.shop, "category": bill.category}
