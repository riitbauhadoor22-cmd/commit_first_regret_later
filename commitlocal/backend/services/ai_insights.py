# services/ai_insights.py — the ONLY code that talks to Groq. It is used only when the user taps
# "Generate Financial Insights" AND the saved analysis is missing or out of date (see routes/insights.py).
# Here: settings from .env (key, model, limits), the prompt, the HTTP call, checking the reply,
# and two small in-memory guards (one request per user at a time; a pause after Groq says "429 too many").
# The API key is read from backend/.env on the server. It never goes to the browser.
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"  # Groq's OpenAI-compatible endpoint
DEFAULT_MODEL = "openai/gpt-oss-20b"
# Models that support Groq "Structured Outputs" with strict: true (console.groq.com/docs/structured-outputs).
# Other models use JSON Object Mode (valid JSON, shape not guaranteed — we still check it below).
STRICT_SCHEMA_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
REASONING_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}  # these accept reasoning_effort
DEFAULT_RETRY_AFTER = 60  # seconds to pause after a 429 that doesn't say how long


# ===== SETTINGS (backend/.env, all optional except the key) =====
@dataclass
class AiSettings:
    api_key: str
    model: str
    daily_limit: int        # AI requests per user per day (UTC day)
    cooldown_seconds: int   # minimum wait between two AI requests of the same user
    max_output_tokens: int  # reply size limit sent to Groq
    max_input_chars: int    # our prompt may not be longer than this
    timeout_seconds: int    # give up waiting for Groq after this


def read_whole_number(name, default):
    try:
        return max(int(os.getenv(name) or default), 0)
    except ValueError:
        return default


def get_settings():
    return AiSettings(
        api_key=(os.getenv("GROQ_API_KEY") or "").strip(),
        model=(os.getenv("GROQ_MODEL") or "").strip() or DEFAULT_MODEL,
        daily_limit=read_whole_number("AI_DAILY_LIMIT", 5),
        cooldown_seconds=read_whole_number("AI_COOLDOWN_SECONDS", 60),
        max_output_tokens=read_whole_number("AI_MAX_OUTPUT_TOKENS", 1000),
        max_input_chars=read_whole_number("AI_MAX_INPUT_CHARS", 6000),
        timeout_seconds=read_whole_number("AI_TIMEOUT_SECONDS", 25),
    )


def log_ai_status():
    """Called once at startup: says whether AI insights are on. NEVER prints the key itself."""
    startup_log = logging.getLogger("uvicorn.error")  # uvicorn shows this logger in the server window
    settings = get_settings()
    if settings.api_key:
        startup_log.info("AI insights: ON (GROQ_API_KEY is set, model %s).", settings.model)
    else:
        startup_log.warning("AI insights: OFF - GROQ_API_KEY is missing in backend/.env. "
                            "The app will offer 'Quick insights (no AI)' instead.")


# ===== WHAT WE EXPECT BACK (checked before saving or showing) =====
class Suggestion(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    reason: str = Field(min_length=1, max_length=400)
    priority: Literal["low", "medium", "high"]


class InsightReply(BaseModel):
    overview: str = Field(min_length=1, max_length=800)
    observations: list[str] = Field(max_length=5)
    suggestions: list[Suggestion] = Field(max_length=3)
    savings_analysis: str = Field(max_length=800)
    encouragement: str = Field(max_length=400)


REPLY_SCHEMA = {  # the same shape for Groq's strict mode: every field required, no extra fields
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                           "reason": {"type": "string"},
                           "priority": {"type": "string", "enum": ["low", "medium", "high"]}},
            "required": ["title", "description", "reason", "priority"],
            "additionalProperties": False}},
        "savings_analysis": {"type": "string"},
        "encouragement": {"type": "string"},
    },
    "required": ["overview", "observations", "suggestions", "savings_analysis", "encouragement"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You explain a young person's monthly finances in plain, kind English (they live in Mauritius).
Rules:
- Use ONLY the figures in the summary. Never invent numbers and never redo the calculations.
- 50/30/20 (needs/wants/savings and debt) is a loose guide, not a rule. Being off it is not a failure.
- Never shame the user. Do not tell them to cut essential needs (rent, food, transport, bills) unless you explain
  why it may be possible and that it is their choice.
- Be specific to these numbers; avoid generic tips. At most 3 suggestions, each framed as educational guidance.
- "information_given" says for each topic: provided, none (the user said they have none = 0) or missing.
  Missing topics are NOT in the summary: they are unknown, never zero. Don't guess them, and don't give advice
  that needs them (e.g. no savings-rate or "money left" advice without income). Say briefly what is missing.
- With little information, give general observations about what IS there and say more data would help.
- Goals with plan "no_plan" or "deadline_passed" have no monthly amount: suggest setting / updating the date instead.
- Write amounts as "Rs 100,000" (groups of three digits).
- Keep every text short (1-3 sentences). Answer with JSON only."""

REPLY_SHAPE = ('{"overview": "...", "observations": ["..."], "suggestions": [{"title": "...", "description": "...", '
               '"reason": "...", "priority": "low|medium|high"}], "savings_analysis": "...", "encouragement": "..."}')


def build_messages(summary):
    """The chat messages for Groq: rules + the compact summary (already anonymous, see financial_analysis.py)."""
    user_text = ("Monthly financial summary (JSON, amounts in Mauritian rupees, already calculated):\n"
                 + json.dumps(summary, separators=(",", ":"))
                 + "\nReply with JSON in exactly this shape: " + REPLY_SHAPE)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}]


def get_prompt_size(messages):
    return sum(len(message["content"]) for message in messages)


# ===== ERRORS =====
class AiUnavailable(Exception):
    """Groq couldn't give a usable answer. code: AI_TIMEOUT, AI_FAILED, AI_RATE_LIMITED or AI_BAD_RESPONSE."""

    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


# ===== THE CALL (one try, never retried automatically) =====
def build_request_body(messages, settings):
    body = {"model": settings.model, "messages": messages, "temperature": 0.2,
            "max_completion_tokens": settings.max_output_tokens}
    if settings.model in STRICT_SCHEMA_MODELS:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "financial_insights", "strict": True, "schema": REPLY_SCHEMA}}
    else:
        body["response_format"] = {"type": "json_object"}
    if settings.model in REASONING_MODELS:
        body["reasoning_effort"] = "low"  # less thinking = fewer tokens used
    return body


def read_retry_after(headers):
    """Seconds Groq asks us to wait (Retry-After header), kept between 1 second and 1 hour."""
    try:
        seconds = float(headers.get("retry-after", DEFAULT_RETRY_AFTER))
    except ValueError:
        seconds = DEFAULT_RETRY_AFTER
    return int(min(max(seconds, 1), 3600))


def send_to_groq(messages, settings):
    """Sends the messages to Groq and returns the reply text. Raises AiUnavailable on any problem."""
    try:
        res = httpx.post(GROQ_URL, json=build_request_body(messages, settings), timeout=settings.timeout_seconds,
                         headers={"Authorization": "Bearer " + settings.api_key})
    except httpx.TimeoutException:
        raise AiUnavailable("AI_TIMEOUT")
    except httpx.HTTPError as error:
        log.warning("Groq request failed: %s", type(error).__name__)
        raise AiUnavailable("AI_FAILED")
    if res.status_code == 429:
        raise AiUnavailable("AI_RATE_LIMITED", read_retry_after(res.headers))
    if res.status_code >= 400:
        log.warning("Groq answered HTTP %s", res.status_code)  # never log the key or the prompt
        raise AiUnavailable("AI_FAILED")
    try:
        return res.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AiUnavailable("AI_BAD_RESPONSE")


def parse_reply(text):
    """Checks the reply's JSON shape. Extra list items are cut off; anything else wrong → AI_BAD_RESPONSE."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        data["observations"] = list(data.get("observations") or [])[:5]
        data["suggestions"] = list(data.get("suggestions") or [])[:3]
        return InsightReply.model_validate(data).model_dump()
    except (ValueError, TypeError, ValidationError):
        raise AiUnavailable("AI_BAD_RESPONSE")


# ===== GUARDS (in memory: one server process) =====
_guard_lock = threading.Lock()
_running = {}            # user_id -> threading.Event, set when that user's request finishes
_paused_until = 0.0      # time.monotonic() until which we don't call Groq (after a 429)


def start_request(user_id):
    """Returns (True, event) if this caller may call Groq now, or (False, event) to wait for the running one."""
    with _guard_lock:
        if user_id in _running:
            return False, _running[user_id]
        event = threading.Event()
        _running[user_id] = event
        return True, event


def finish_request(user_id):
    with _guard_lock:
        event = _running.pop(user_id, None)
    if event:
        event.set()


def pause_groq(seconds):
    global _paused_until
    with _guard_lock:
        _paused_until = max(_paused_until, time.monotonic() + seconds)


def get_pause_seconds():
    """How many seconds are left of the pause after a 429 (0 = Groq can be called)."""
    return max(int(_paused_until - time.monotonic() + 0.999), 0)


def reset_guards():
    """For tests: forget running requests and pauses."""
    global _paused_until
    with _guard_lock:
        _running.clear()
        _paused_until = 0.0
