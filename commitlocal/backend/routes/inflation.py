# routes/inflation.py — /api/inflation/projection: a live inflation estimate for the create/edit goal form
# (nothing is saved). The maths lives in services/inflation.py. Data: Statistics Mauritius CPI.
import datetime
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from categories import GOAL_CPI_CATEGORIES
from errors import AppError
from models import MAX_AMOUNT
from routes.auth import require_user
from services.inflation import project_goal

router = APIRouter(prefix="/api/inflation")


# ===== ROUTES =====
@router.get("/projection")
def preview_projection(target: float = Query(gt=0, le=MAX_AMOUNT),
                       deadline: datetime.date = Query(),
                       current: float = Query(default=0, ge=0, le=MAX_AMOUNT),
                       category: Optional[str] = Query(default=None, max_length=30),
                       period: Literal["12m", "3y"] = "12m",
                       user_id: uuid.UUID = Depends(require_user)):
    if category and category not in GOAL_CPI_CATEGORIES:
        raise AppError(400, "INVALID_CATEGORY", "Pick one of: " + ", ".join(GOAL_CPI_CATEGORIES))
    return project_goal(target, current, deadline, category or None, years=3 if period == "3y" else 1)
