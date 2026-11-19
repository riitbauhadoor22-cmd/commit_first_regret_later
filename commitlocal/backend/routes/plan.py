# routes/plan.py — "My budget plan". The commitment rules are enforced HERE (not only in the screen):
#   GET    /api/plan?today=         → current plan, pending change, this month vs the plan, streak, last month's
#                                     result + tips, the recommendation, history, all plans (looser / stricter)
#   POST   /api/plan/start/preview  → {life, pays_rent, has_loan, irregular_income} → suggested plan (nothing saved)
#   POST   /api/plan/start          → the first plan (only while the user has none); starts this month
#   GET    /api/plan/preview?plan_id= → what switching costs (Rs saved less a month, goal months later)
#   POST   /api/plan/change         → schedule a change (starts on the 1st of next month; stricter may start now)
#   DELETE /api/plan/pending        → cancel the change that hasn't started yet
# Rules: one change per calendar month; looser plans (less saving or more wants) start next month only, need a
# second confirm and a reason. Month results are worked out when viewed (never stored), each against the plan
# that was active in that month.
# "today" = the phone's date (within 2 days of the server's). DEMO_TODAY=YYYY-MM-DD in .env moves the plan's date
# for a demo (e.g. to next month); it is ignored in production.
import datetime
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from budget_plans import PLANS, REFERENCES, RESEARCH_IDEAS, is_looser
from config import is_production
from database import find_savings_row, get_user_rows, open_db, read_savings_values
from errors import AppError
from info_status import get_info_status
from models import Deposit, Expense, Income, MyLoan, PlanChangeForm, PlanPeriod, PlanStartForm, SavingsGoal
from money import sort_goals_by_priority
from routes.auth import require_user
from routes.dashboard import pick_today
from routes.info import get_choices
from services.budget_plan import (active_period, add_months, build_recommendation, count_streak,
                                  has_enough_data, judge_month, month_figures, month_tips, pending_period,
                                  plan_progress, suggest_start_plan, switch_cost)

router = APIRouter(prefix="/api/plan")

MAX_MONTHS_JUDGED = 24  # finished months shown at most this far back


# ===== HELPERS =====
def plan_today(today=None):
    """The date the plan works with: DEMO_TODAY (development only), else the phone's date, else the server's."""
    demo = (os.getenv("DEMO_TODAY") or "").strip()
    if demo and not is_production():
        try:
            return datetime.date.fromisoformat(demo).isoformat()
        except ValueError:
            pass
    return pick_today(today).isoformat()


def read_rows(db, user_id):
    savings_row = find_savings_row(db, user_id)
    return {"incomes": get_user_rows(db, Income, user_id), "expenses": get_user_rows(db, Expense, user_id),
            "loans": get_user_rows(db, MyLoan, user_id), "deposits": get_user_rows(db, Deposit, user_id),
            "goals": get_user_rows(db, SavingsGoal, user_id), "savings": read_savings_values(db, user_id),
            "savings_row": savings_row.to_dict() if savings_row else None, "choices": get_choices(db, user_id),
            "periods": get_user_rows(db, PlanPeriod, user_id)}


def figures_for(rows, month):
    info = get_info_status(rows["incomes"], rows["expenses"], rows["deposits"], rows["goals"], rows["savings_row"],
                           rows["loans"], rows["choices"], month)
    return month_figures(rows["incomes"], rows["expenses"], rows["loans"], rows["savings"], info, month,
                         rows["deposits"])


def find_periods(db, user_id):
    return list(db.scalars(select(PlanPeriod).where(PlanPeriod.user_id == user_id)))


def month_results(rows, this_month):
    """Each finished month (since the first plan, at most 24 back) judged against the plan active in it, worked out
    NOW from the data, like every other summary number: expenses logged late still count. Switching plans can't
    change a past month, because each month's plan comes from the plan history, whose past rows never change."""
    periods = rows["periods"]
    if not periods:
        return []
    month = max(min(p["start_month"] for p in periods), add_months(this_month, -MAX_MONTHS_JUDGED))
    results = []
    while month < this_month:
        period = active_period(periods, month)
        if period:
            results.append({"month": month, "plan_id": period["plan_id"],
                            **judge_month(figures_for(rows, month), period["plan_id"])})
        month = add_months(month, 1)
    return results


def changed_this_month(periods, this_month):
    """The one change a month is used up (the very first plan doesn't count)."""
    return any(p["requested_month"] == this_month and p["reason"] != "start" for p in periods)


def suggestion_month(rows, this_month):
    """The month the suggestion looks at: last month if it has expenses, otherwise this month so far."""
    last = add_months(this_month, -1)
    return last if any(e["date"][:7] == last for e in rows["expenses"]) else this_month


def recommendation_for(rows, current_plan_id, today):
    """Day one: nothing (the start questions picked the style). After 14+ days or 10+ expenses: a suggestion from
    real spending (services/budget_plan.build_recommendation)."""
    if not has_enough_data(rows["expenses"], today):
        return {"action": "wait"}
    return build_recommendation(figures_for(rows, suggestion_month(rows, today[:7])), current_plan_id)


def first_goal(goals):
    """The goal a looser plan would slow down: the most important one not reached yet."""
    open_goals = [g for g in goals if g["target_amount"] and g["saved_amount"] < g["target_amount"]]
    return sort_goals_by_priority(open_goals)[0] if open_goals else None


def reference_income(rows, this_month):
    """Income used for "you'd save Rs X less": this month's, else last month's."""
    for month in (this_month, add_months(this_month, -1)):
        income = figures_for(rows, month)["income"]
        if income:
            return income
    return 0


def compare(plan_id, current_id):
    """looser / stricter / same (same savings and wants %) / current, compared with the current plan."""
    if not current_id or plan_id == current_id:
        return "current" if plan_id == current_id else None
    if is_looser(plan_id, current_id):
        return "looser"
    new, now = PLANS[plan_id], PLANS[current_id]
    return "same" if (new["savings"], new["wants"]) == (now["savings"], now["wants"]) else "stricter"


def plan_list(current_id):
    return [{"id": plan_id, **plan, "compared": compare(plan_id, current_id)} for plan_id, plan in PLANS.items()]


def build_state(db, user_id, today):
    """Everything the plan card and screens show."""
    this_month = today[:7]
    rows = read_rows(db, user_id)
    results = month_results(rows, this_month)
    periods = rows["periods"]
    current = active_period(periods, this_month)
    state = {"today": today, "month": this_month, "next_month": add_months(this_month, 1),
             "has_plan": current is not None, "plans": plan_list(current["plan_id"] if current else None),
             "references": REFERENCES, "research_ideas": RESEARCH_IDEAS}
    if current is None:
        return state
    pending = pending_period(periods, this_month)
    this_figures = figures_for(rows, this_month)
    last = results[-1] if results and results[-1]["month"] == add_months(this_month, -1) else None
    state.update({
        "current": {"plan_id": current["plan_id"], "start_month": current["start_month"], "reason": current["reason"]},
        "pending": {"plan_id": pending["plan_id"], "start_month": pending["start_month"]} if pending else None,
        "changed_this_month": changed_this_month(periods, this_month),
        # when the style last changed (plan_history.created_at): it can change once per calendar month
        "style_changed_at": max(p["created_at"] for p in periods),
        "progress": plan_progress(this_figures, current["plan_id"]),
        "savings_status": this_figures["savings_status"],  # the same encouraging message as the Money card
        "streak": count_streak(results),
        "last_result": {**last, "tips": month_tips(last)} if last else None,
        "recommendation": None if pending else recommendation_for(rows, current["plan_id"], today),
        "history": sorted(periods, key=lambda p: (p["start_month"], p["created_at"]), reverse=True),
        "results": list(reversed(results)),
    })
    return state


# ===== ROUTES =====
@router.get("")
def read_plan(today: Optional[datetime.date] = Query(default=None), user_id: uuid.UUID = Depends(require_user)):
    with open_db() as db:
        return build_state(db, user_id, plan_today(today))


@router.post("/start/preview")
def preview_start(form: PlanStartForm, user_id: uuid.UUID = Depends(require_user)):
    plan_id, reason = suggest_start_plan(form.life, form.pays_rent, form.has_loan, form.irregular_income)
    return {"plan_id": plan_id, "reason": reason}


@router.post("/start", status_code=201)
def start_plan(form: PlanStartForm, user_id: uuid.UUID = Depends(require_user)):
    """The first plan only: any plan may be picked here, no commitment rules yet. Starts this month."""
    today = plan_today(form.today)
    suggested, reason = suggest_start_plan(form.life, form.pays_rent, form.has_loan, form.irregular_income)
    with open_db() as db:
        if find_periods(db, user_id):
            raise AppError(409, "PLAN_ALREADY_SET", "You already have a plan. Use 'Change plan' instead.")
        plan_id = form.plan_id or suggested
        db.add(PlanPeriod(user_id=user_id, plan_id=plan_id, start_month=today[:7], reason="start",
                          reason_note=reason, was_recommended=plan_id == suggested, requested_month=today[:7]))
        db.flush()
        return build_state(db, user_id, today)


@router.get("/preview")
def preview_change(plan_id: str = Query(), today: Optional[datetime.date] = Query(default=None),
                   user_id: uuid.UUID = Depends(require_user)):
    if plan_id not in PLANS:
        raise AppError(422, "INVALID_PLAN", "Pick one of the listed plans.")
    today = plan_today(today)
    with open_db() as db:
        rows = read_rows(db, user_id)
    current = active_period(rows["periods"], today[:7])
    if current is None:
        raise AppError(400, "NO_PLAN_YET", "Choose your first plan first.")
    looser = is_looser(plan_id, current["plan_id"])
    cost = switch_cost(current["plan_id"], plan_id, reference_income(rows, today[:7]), first_goal(rows["goals"]))
    return {"plan_id": plan_id, "looser": looser, "starts": add_months(today[:7], 1), **cost}


@router.post("/change")
def change_plan(form: PlanChangeForm, user_id: uuid.UUID = Depends(require_user)):
    today = plan_today(form.today)
    this_month = today[:7]
    with open_db() as db:
        periods = find_periods(db, user_id)
        period_dicts = [p.to_dict() for p in periods]
        current_dict = active_period(period_dicts, this_month)
        if current_dict is None:
            raise AppError(400, "NO_PLAN_YET", "Choose your first plan first.")
        if form.plan_id == current_dict["plan_id"]:
            raise AppError(400, "SAME_PLAN", "That is already your plan.")
        if changed_this_month(period_dicts, this_month):
            raise AppError(409, "PLAN_CHANGE_LIMIT", "You can change your plan once a month. "
                           "Cancel the change you asked for if you want a different one.")
        looser = is_looser(form.plan_id, current_dict["plan_id"])
        rows = read_rows(db, user_id)
        advice = recommendation_for(rows, current_dict["plan_id"], today) if form.from_recommendation else {}
        # only a switch the engine really suggests right now counts as recommended (no friction for it)
        recommended = advice.get("action") == "switch" and advice.get("plan_id") == form.plan_id
        if looser and form.start_now:
            raise AppError(400, "LOOSER_STARTS_NEXT_MONTH", "A plan with less saving starts next month, "
                           "so this month still counts.")
        if looser and not recommended:  # friction: cost shown, a second confirm and a reason
            if not form.confirm_looser:
                cost = switch_cost(current_dict["plan_id"], form.plan_id, reference_income(rows, this_month),
                                   first_goal(rows["goals"]))
                raise AppError(409, "CONFIRM_LOOSER", "This plan saves less. Please confirm.",
                               {"save_less": cost["save_less"], "goal": cost["goal"]})
            if form.reason is None:
                raise AppError(400, "REASON_REQUIRED", "Please tell us why you want to change.")

        current = next(p for p in periods if str(p.id) == current_dict["id"])
        start = this_month if form.start_now else add_months(this_month, 1)
        if form.start_now:  # stricter only: the new plan judges this month
            current.end_month = this_month if current.start_month == this_month else add_months(this_month, -1)
        else:
            current.end_month = this_month
        db.add(PlanPeriod(user_id=user_id, plan_id=form.plan_id, start_month=start,
                          reason="recommended" if recommended else (form.reason or "stricter"),
                          reason_note=form.reason_note.strip(), was_recommended=recommended,
                          requested_month=this_month))
        db.flush()
        return build_state(db, user_id, today)


@router.delete("/pending")
def cancel_pending(today: Optional[datetime.date] = Query(default=None), user_id: uuid.UUID = Depends(require_user)):
    """Cancel a change that hasn't started yet: the current plan simply keeps running."""
    today = plan_today(today)
    this_month = today[:7]
    with open_db() as db:
        periods = find_periods(db, user_id)
        pending = next((p for p in periods if p.start_month > this_month), None)
        if pending is None:
            raise AppError(404, "NO_PENDING_CHANGE", "There is no plan change waiting.")
        db.delete(pending)
        for period in periods:
            if period is not pending and period.end_month == this_month:
                period.end_month = None
        db.flush()
        return build_state(db, user_id, today)

