# routes/insights.py — "Financial insights" on the Money tab.
#   GET  /api/insights?month=YYYY-MM   → the 50/30/20 check-up (plain maths) + the SAVED AI analysis. Never calls Groq.
#   POST /api/insights/generate        → only when the user taps the button. Calls Groq only if the saved analysis
#                                        is missing or out of date, and only within the limits below.
# Order of checks in generate: saved one still valid? → enough information given? → key set? → someone already asking? → paused after a 429?
# → daily limit → cooldown → prompt size → ONE call to Groq (never retried) → check the reply → save it.
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from database import get_user_rows, open_db, read_savings_values
from errors import AppError
from models import (AiRequestLog, Deposit, Expense, Income, InsightRequestForm, MyLoan, SavedInsight, SavingsGoal,
                    iso, utc_now)
from money import get_this_month, get_today
from routes.auth import require_user
from routes.info import read_info_status
from routes.summary import MONTH_PATTERN
from services import ai_insights
from services.financial_analysis import analyse_month, build_ai_summary, get_fingerprint

router = APIRouter(prefix="/api/insights")


# ===== HELPERS =====
def get_analysis(db, user_id, month):
    """The plain-maths check-up for one month (no AI)."""
    return analyse_month(get_user_rows(db, Income, user_id), get_user_rows(db, Expense, user_id),
                         get_user_rows(db, Deposit, user_id), get_user_rows(db, SavingsGoal, user_id),
                         read_savings_values(db, user_id), get_user_rows(db, MyLoan, user_id),
                         read_info_status(db, user_id, month), month, get_today())


def find_saved(db, user_id, month):
    return db.scalar(select(SavedInsight).where(SavedInsight.user_id == user_id, SavedInsight.month == month))


def describe_saved(saved, fingerprint):
    """status: none (never made) / fresh (same data) / outdated (data changed since — user may refresh)."""
    if saved is None:
        return {"status": "none", "insight": None, "generated_at": None, "model": None}
    return {"status": "fresh" if saved.fingerprint == fingerprint else "outdated",
            "insight": json.loads(saved.content), "generated_at": iso(saved.created_at) + "Z", "model": saved.model}


def get_usage(db, user_id, settings):
    """AI requests used today (UTC day) and seconds left before the next one is allowed."""
    now = utc_now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    mine = AiRequestLog.user_id == user_id
    used = db.scalar(select(func.count()).select_from(AiRequestLog).where(mine, AiRequestLog.created_at >= day_start))
    last = db.scalar(select(func.max(AiRequestLog.created_at)).where(mine))
    wait = 0
    if last is not None:
        wait = max(int(settings.cooldown_seconds - (now - last).total_seconds() + 0.999), 0)
    return {"used_today": used, "daily_limit": settings.daily_limit, "cooldown_seconds_left": wait}


def build_reply(db, user_id, month, settings, cached=None):
    analysis = get_analysis(db, user_id, month)
    fingerprint = get_fingerprint(build_ai_summary(analysis))
    reply = {"analysis": analysis, "saved": describe_saved(find_saved(db, user_id, month), fingerprint),
             "usage": get_usage(db, user_id, settings), "ai_configured": bool(settings.api_key),
             "paused_seconds": ai_insights.get_pause_seconds()}
    if cached is not None:
        reply["cached"] = cached
    return reply


def save_insight(db, user_id, month, fingerprint, model, insight):
    """One saved analysis per user and month: replaced by the newest."""
    saved = find_saved(db, user_id, month)
    if saved is None:
        saved = SavedInsight(user_id=user_id, month=month)
        db.add(saved)
    saved.fingerprint = fingerprint
    saved.model = model
    saved.content = json.dumps(insight)
    saved.created_at = utc_now()


def set_log_outcome(log_id, outcome):
    with open_db() as db:
        row = db.get(AiRequestLog, log_id)
        if row is not None:
            row.outcome = outcome


def wait_error(code, message, seconds):
    error = AppError(429 if code != "AI_RATE_LIMITED" else 503, code, message, {"seconds": seconds})
    error.headers = {"Retry-After": str(seconds)}
    return error


# ===== ONE GENERATION (only the caller that holds the user's guard gets here) =====
def run_generation(user_id, month, summary, fingerprint, messages, settings):
    paused = ai_insights.get_pause_seconds()
    if paused:
        raise wait_error("AI_RATE_LIMITED", "AI insights are busy right now. Please try again later.", paused)
    with open_db() as db:
        usage = get_usage(db, user_id, settings)
        if usage["used_today"] >= settings.daily_limit:
            raise AppError(429, "AI_DAILY_LIMIT", "You've used today's AI analyses. Your numbers still work; "
                           "try again tomorrow.", {"limit": settings.daily_limit})
        if usage["cooldown_seconds_left"]:
            raise wait_error("AI_COOLDOWN", "Please wait a moment before asking again.",
                             usage["cooldown_seconds_left"])
        log_row = AiRequestLog(user_id=user_id, month=month, model=settings.model, outcome="started")
        db.add(log_row)  # counted BEFORE the call, so a crash can't give free extra requests
    try:
        insight = ai_insights.parse_reply(ai_insights.send_to_groq(messages, settings))
    except ai_insights.AiUnavailable as problem:
        set_log_outcome(log_row.id, problem.code)
        if problem.code == "AI_RATE_LIMITED":
            ai_insights.pause_groq(problem.retry_after)
            raise wait_error("AI_RATE_LIMITED", "AI insights are busy right now. Please try again later.",
                             problem.retry_after)
        raise AppError(502, problem.code, "New AI insights are unavailable right now. Your numbers still work.")
    with open_db() as db:
        save_insight(db, user_id, month, fingerprint, settings.model, insight)
        row = db.get(AiRequestLog, log_row.id)
        row.outcome = "ok"
    with open_db() as db:
        return build_reply(db, user_id, month, settings, cached=False)


# ===== ROUTES =====
@router.get("")
def read_insights(month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
                  user_id: uuid.UUID = Depends(require_user)):
    """Shown every time the Money tab loads: maths + saved analysis. No AI call here."""
    with open_db() as db:
        return build_reply(db, user_id, month or get_this_month(), ai_insights.get_settings())


@router.post("/generate")
def generate_insights(form: InsightRequestForm, user_id: uuid.UUID = Depends(require_user)):
    settings = ai_insights.get_settings()
    month = form.month or get_this_month()
    with open_db() as db:
        analysis = get_analysis(db, user_id, month)
        summary = build_ai_summary(analysis)
        fingerprint = get_fingerprint(summary)
        saved = find_saved(db, user_id, month)
        if saved is not None and saved.fingerprint == fingerprint:  # nothing changed → reuse, no AI call
            return build_reply(db, user_id, month, settings, cached=True)
    if not analysis["enough_for_ai"]:  # nothing given yet: explain instead of asking the AI to guess
        raise AppError(400, "AI_NOT_ENOUGH_DATA", "Add some income, expenses, savings or a loan first.")
    if not settings.api_key:
        raise AppError(503, "AI_NOT_CONFIGURED", "AI insights are not set up on this server.")
    messages = ai_insights.build_messages(summary)
    if ai_insights.get_prompt_size(messages) > settings.max_input_chars:
        raise AppError(400, "AI_INPUT_TOO_LARGE", "There is too much data to analyse in one go.")

    is_first, finished = ai_insights.start_request(user_id)
    if not is_first:  # the same user already asked (double tap, second tab): wait for that answer and share it
        finished.wait(settings.timeout_seconds + 5)
        with open_db() as db:
            saved = find_saved(db, user_id, month)
            if saved is not None and saved.fingerprint == fingerprint:
                return build_reply(db, user_id, month, settings, cached=True)
        raise AppError(409, "AI_IN_PROGRESS", "Your analysis is already being made. Please wait.")
    try:
        return run_generation(user_id, month, summary, fingerprint, messages, settings)
    finally:
        ai_insights.finish_request(user_id)
