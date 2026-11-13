# routes/game.py — /api/game: the Arcade "Budget Challenge". Start a game (attempt_id + random event chosen here),
# submit an allocation (first try → the event is revealed; final → score + XP, given ONCE per attempt), list past results.
# Only touches the game_attempts table: real income / expenses / budgets are never read or changed.
import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update

from database import find_user_row, open_db
from errors import AppError
from game.budget_engine import check_within_income, clean_allocation
from game.events import choose_event
from game.scenarios import LEVELS, POINTS, XP_FIRST_COMPLETION_BONUS, get_event, get_level
from game.scoring import score_allocation
from models import GameAttempt, GameStartForm, GameSubmitForm, utc_now
from routes.auth import require_user

router = APIRouter(prefix="/api/game")


# ===== HELPERS =====
def find_level(number):
    level = get_level(number)
    if level is None:
        raise AppError(404, "GAME_LEVEL_NOT_FOUND", "That level doesn't exist.")
    return level


def build_reply(attempt, level, result, xp_awarded=0, bonus=False, already=False):
    event = get_event(level, attempt.event) if attempt.event else None
    return {"attempt_id": str(attempt.id), "level": attempt.level, "stage": attempt.stage,
            "event": event if attempt.stage != "start" else None,  # the event stays secret until the first submit
            **result, "xp_awarded": xp_awarded, "first_completion_bonus": bonus, "already_completed": already}


# ===== ROUTES =====
@router.get("/levels")
def list_levels(user_id: uuid.UUID = Depends(require_user)):
    return {"levels": LEVELS, "points": POINTS, "first_completion_bonus": XP_FIRST_COMPLETION_BONUS}


@router.post("/attempts", status_code=201)
def start_attempt(form: GameStartForm, user_id: uuid.UUID = Depends(require_user)):
    level = find_level(form.level)
    events_on = form.events_on  # every level can turn surprise events off (then the 10 event points are automatic)
    event = choose_event(level, events_on)  # picked now, kept secret until the first submit
    with open_db() as db:
        attempt = GameAttempt(user_id=user_id, level=level["level"], events_on=events_on,
                              event=event["id"] if event else None, stage="start", xp=0, xp_awarded=False)
        db.add(attempt)
        db.flush()
        return {"attempt_id": str(attempt.id), "level": level, "events_on": events_on, "has_event": event is not None}


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: uuid.UUID, form: GameSubmitForm, user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        attempt = find_user_row(db, GameAttempt, attempt_id, user_id)
        if attempt is None:
            raise AppError(404, "GAME_NOT_FOUND", "Game not found.")
        level = find_level(attempt.level)
        event = get_event(level, attempt.event) if attempt.event else None

        # Already finished: show the saved result again, but never give XP twice
        if attempt.stage == "done":
            saved = json.loads(attempt.allocation)  # stored in cents
            return build_reply(attempt, level, score_allocation(level, saved, event), already=True)

        allocation = clean_allocation(level, form.allocation)  # {category: cents}

        # First try: score without the event, then reveal it (the player may adjust once)
        if not form.final:
            if attempt.stage == "event":
                raise AppError(400, "GAME_FINAL_NEEDED", "You already adjusted once: submit your final budget.")
            check_within_income(level, allocation, None)  # over income is blocked
            result = score_allocation(level, allocation, event, event_applied=False)
            if event is not None:
                attempt.stage = "event"
            return build_reply(attempt, level, result)

        if event is not None and attempt.stage != "event":
            raise AppError(400, "GAME_EVENT_PENDING", "Submit your first budget to see the surprise event.")

        # Final submit: score with the event, XP = score (+ bonus the first time this level is completed)
        check_within_income(level, allocation, event)
        result = score_allocation(level, allocation, event)
        done_before = db.scalar(select(func.count()).select_from(GameAttempt).where(
            GameAttempt.user_id == user_id, GameAttempt.level == attempt.level, GameAttempt.stage == "done"))
        bonus = done_before == 0
        xp = result["score"] + (XP_FIRST_COMPLETION_BONUS if bonus else 0)
        # Only updates the row if XP wasn't given yet (safe even if the same submit arrives twice at once)
        changed = db.execute(update(GameAttempt).where(GameAttempt.id == attempt.id, GameAttempt.xp_awarded.is_(False))
                             .values(stage="done", score=result["score"], xp=xp, xp_awarded=True, completed_at=utc_now(),
                                     allocation=json.dumps(allocation)))
        if changed.rowcount != 1:
            return build_reply(attempt, level, result, already=True)
        attempt.stage = "done"
        return build_reply(attempt, level, result, xp_awarded=xp, bonus=bonus)


@router.get("/attempts")
def list_attempts(user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        rows = db.scalars(select(GameAttempt).where(GameAttempt.user_id == user_id, GameAttempt.stage == "done")
                          .order_by(GameAttempt.completed_at.desc())).all()
        best = {}
        for row in rows:
            best[row.level] = max(best.get(row.level, 0), row.score or 0)
        return {"attempts": [row.to_dict() for row in rows[:30]],  # newest 30 for "previous results"
                "total_xp": sum(row.xp for row in rows),
                "best_scores": {str(level): score for level, score in best.items()}}
