# test_insights.py — Financial insights: the plain-maths check-up and the Groq rules (call only when asked,
# reuse saved results, outdated after real changes, cooldown, daily limit, one request at a time, errors / 429,
# works with no key, other users can't see it). Groq is ALWAYS faked (conftest.py: fake_groq). All data is fictional.
import threading
from datetime import timedelta

import httpx
import pytest

import database
from conftest import log_in
from models import AiRequestLog
from money import get_this_month, get_today
from services import ai_insights
from services.ai_insights import AiUnavailable, build_request_body, get_settings, send_to_groq
from services.financial_analysis import analyse_month, build_ai_summary, get_fingerprint, get_previous_month

MONTH = get_this_month()
TODAY = get_today()


# ===== HELPERS =====
def add_month_data(client):
    """Fictional month: income 20,000 · needs 8,000 · wants 4,000 · a goal with 2,000 put in."""
    assert client.post("/api/income", json={"name": "Job", "type": "Salary", "amount": 20000,
                                            "frequency": "monthly", "date": TODAY}).status_code == 201
    assert client.post("/api/expenses", json={"amount": 8000, "category": "Groceries", "note": "Secret shop",
                                              "date": TODAY}).status_code == 201
    assert client.post("/api/expenses", json={"amount": 4000, "category": "Shopping", "date": TODAY}).status_code == 201
    assert client.post("/api/goals", json={"name": "Private laptop", "target_amount": 30000,
                                           "deadline": "2027-12-01", "priority": 1}).status_code == 201
    goal_id = client.get("/api/goals").json()["goals"][0]["id"]
    assert client.post(f"/api/goals/{goal_id}/add-money", json={"amount": 2000}).status_code == 200
    # Savings this month = the monthly saving target (the goal deposit is bank money, not counted again)
    assert client.put("/api/savings", json={"monthly_target": 2000}).status_code == 200


def generate(client):
    return client.post("/api/insights/generate", json={"month": MONTH})


def forget_cooldown():
    """Pretend every AI request happened 2 hours ago (instead of really waiting)."""
    with database.open_db() as db:
        for row in db.query(AiRequestLog):
            row.created_at -= timedelta(hours=2)


@pytest.fixture
def user(logged_in):
    add_month_data(logged_in)
    return logged_in


# ===== PLAIN MATHS (no AI) =====
NO_SAVINGS = {"monthly_target": None, "safety_net_saved": 0}


def info(income="provided", expenses="provided", loans="missing", savings="missing"):
    return {"income": income, "expenses": expenses, "loans": loans, "savings": savings}


def test_check_up_numbers(user):
    data = user.get(f"/api/insights?month={MONTH}").json()["analysis"]
    assert data["take_home_income"] == 20000 and data["needs"] == 8000 and data["wants"] == 4000
    assert data["savings"] == 2000 and data["remaining"] == 6000 and data["remaining_excludes_loans"] is True
    split = {row["group"]: row for row in data["split"]}
    assert split["needs"]["percent"] == 40 and split["needs"]["difference_points"] == -10
    assert split["wants"]["percent"] == 20 and split["savings_and_debt"]["percent"] == 10
    # Loans not given: savings & debt is incomplete, so it is NOT compared with 20% (no "savings below" note)
    assert split["savings_and_debt"]["difference_points"] is None and split["savings_and_debt"]["complete"] is False
    assert all(note["code"] != "SAVINGS_BELOW" for note in data["observations"])
    assert data["loan_repayments"] is None and "NO_LOANS" in data["data_gaps"]
    assert data["goals"][0]["percent"] == pytest.approx(6.7, abs=0.1)


def test_check_up_with_loans_known(user):
    user.put("/api/info-choices", json={"topic": "loans", "none": True})  # "I don't have a loan" = 0
    data = user.get(f"/api/insights?month={MONTH}").json()["analysis"]
    assert data["loan_repayments"] == 0 and data["remaining_excludes_loans"] is False
    split = {row["group"]: row for row in data["split"]}
    assert split["savings_and_debt"]["difference_points"] == -10
    assert {"code": "SAVINGS_BELOW", "params": {"points": 10}} in data["observations"]
    user.post("/api/my-loans", json={"balance": 50000, "annual_rate": 9, "monthly_payment": 2000})
    data = user.get(f"/api/insights?month={MONTH}").json()["analysis"]
    assert data["loan_repayments"] == 2000 and data["remaining"] == 4000  # 20,000 − 8,000 − 4,000 − 2,000 − 2,000
    assert {row["group"]: row for row in data["split"]}["savings_and_debt"]["percent"] == 20


def test_no_income_says_so_instead_of_guessing():
    expense = {"amount": 500, "category": "Food & drinks", "kind": "want", "date": "2026-11-02", "is_fixed": 0}
    data = analyse_month([], [expense], [], [], NO_SAVINGS, [], info(income="missing"), "2026-11", "2026-11-14")
    assert data["take_home_income"] is None and data["remaining"] is None
    assert all(row["percent"] is None for row in data["split"])
    assert "NO_INCOME" in data["data_gaps"]
    assert not any(note["code"] in ("OVER_INCOME", "SAVINGS_BELOW", "WITHIN_GUIDE") for note in data["observations"])


def test_missing_expenses_are_not_zero():
    income = [{"amount": 20000, "frequency": "monthly", "date": "2026-11-01"}]
    data = analyse_month(income, [], [], [], NO_SAVINGS, [], info(expenses="missing"), "2026-11", "2026-11-14")
    assert data["needs"] is None and data["wants"] is None and data["remaining"] is None
    assert data["categories"] == [] and data["safety_net"] is None and "NO_EXPENSES" in data["data_gaps"]
    summary = build_ai_summary(data)
    assert "needs" not in summary and "remaining" not in summary and summary["take_home_income"] == 20000


def test_spending_change_vs_last_month():
    expenses = [{"amount": 1000, "category": "Other", "kind": "need", "date": "2026-10-05", "is_fixed": 0},
                {"amount": 1500, "category": "Other", "kind": "need", "date": "2026-11-05", "is_fixed": 0}]
    data = analyse_month([], expenses, [], [], NO_SAVINGS, [], info(income="missing"), "2026-11", "2026-11-14")
    assert data["spending_change"]["change_percent"] == 50
    assert {"code": "SPENDING_UP", "params": {"percent": 50}} in data["observations"]
    assert get_previous_month("2026-01") == "2025-12"


def test_fingerprint_ignores_tiny_changes_but_not_real_ones():
    income = [{"amount": 20000, "frequency": "monthly", "date": "2026-11-01"}]

    def fingerprint(amount):
        expense = {"amount": amount, "category": "Groceries", "kind": "need", "date": "2026-11-02", "is_fixed": 0}
        return get_fingerprint(build_ai_summary(analyse_month(income, [expense], [], [], NO_SAVINGS, [], info(),
                                                              "2026-11", "2026-11-14")))

    assert fingerprint(5000) == fingerprint(5010)   # Rs 10 difference: same analysis
    assert fingerprint(5000) != fingerprint(6000)   # Rs 1,000 difference: outdated


def test_summary_sent_to_ai_has_no_personal_text(user, fake_groq):
    assert generate(user).status_code == 200
    sent = str(fake_groq["last_messages"])
    for private in ("Private laptop", "Secret shop", "asha@example.com", "Asha", "Job"):
        assert private not in sent
    assert "Goal 1" in sent and "NO_LOANS" in sent and "loan_repayments" not in sent  # unknown loans left out


def test_request_body_is_small_and_structured():
    settings = get_settings()
    body = build_request_body([{"role": "user", "content": "x"}], settings)
    assert body["model"] == "openai/gpt-oss-20b" and body["temperature"] <= 0.3
    assert body["max_completion_tokens"] == 1000
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"]
    settings.model = "llama-3.3-70b-versatile"
    assert build_request_body([], settings)["response_format"] == {"type": "json_object"}


# ===== 1. GENERATE =====
def test_generate_with_complete_data(user, fake_groq):
    res = generate(user)
    assert res.status_code == 200
    body = res.json()
    assert body["cached"] is False and fake_groq["calls"] == 1
    assert body["saved"]["status"] == "fresh" and body["saved"]["model"] == "openai/gpt-oss-20b"
    assert body["saved"]["insight"]["suggestions"][0]["priority"] == "medium"
    assert body["saved"]["generated_at"].endswith("Z") and body["usage"]["used_today"] == 1


# ===== 2 + 3. LOADING AND NAVIGATING NEVER CALL GROQ =====
def test_dashboard_loads_reuse_the_saved_analysis(user, fake_groq):
    generate(user)
    for _ in range(10):
        body = user.get(f"/api/insights?month={MONTH}").json()
        assert body["saved"]["status"] == "fresh" and body["saved"]["insight"]["overview"]
    assert fake_groq["calls"] == 1


def test_navigating_between_tabs_never_calls_groq(user, fake_groq):
    for _ in range(3):
        for path in (f"/api/summary?month={MONTH}", f"/api/insights?month={MONTH}", "/api/expenses/quick",
                     f"/api/income?month={MONTH}", "/api/savings", "/api/goals", "/api/game/levels",
                     "/api/game/attempts"):
            assert user.get(path).status_code == 200, path
    assert fake_groq["calls"] == 0
    assert user.get(f"/api/insights?month={MONTH}").json()["saved"]["status"] == "none"


# ===== 4 + 5 + 6. CHANGES MAKE IT OUTDATED; ONLY THE BUTTON REFRESHES =====
def test_adding_an_expense_does_not_call_groq_but_marks_outdated(user, fake_groq):
    generate(user)
    user.post("/api/expenses", json={"amount": 3000, "category": "Fun & outings", "date": TODAY})
    assert fake_groq["calls"] == 1
    saved = user.get(f"/api/insights?month={MONTH}").json()["saved"]
    assert saved["status"] == "outdated" and saved["insight"]["overview"]  # old analysis still shown


def test_editing_income_marks_outdated(user):
    generate(user)
    income_id = user.get(f"/api/income?month={MONTH}").json()["regular"][0]["id"]
    user.put(f"/api/income/{income_id}", json={"name": "Job", "type": "Salary", "amount": 25000,
                                               "frequency": "monthly", "date": TODAY})
    assert user.get(f"/api/insights?month={MONTH}").json()["saved"]["status"] == "outdated"


def test_refreshing_an_outdated_analysis(user, fake_groq):
    generate(user)
    user.post("/api/expenses", json={"amount": 3000, "category": "Fun & outings", "date": TODAY})
    forget_cooldown()
    res = generate(user)
    assert res.status_code == 200 and res.json()["cached"] is False
    assert res.json()["saved"]["status"] == "fresh" and fake_groq["calls"] == 2


# ===== 7. REPEATED CLICKS =====
def test_clicking_refresh_again_and_again(user, fake_groq):
    generate(user)
    for _ in range(5):
        res = generate(user)
        assert res.status_code == 200 and res.json()["cached"] is True
    assert fake_groq["calls"] == 1


def test_cooldown_after_a_change(user, fake_groq):
    generate(user)
    user.post("/api/expenses", json={"amount": 3000, "category": "Fun & outings", "date": TODAY})
    res = generate(user)
    assert res.status_code == 429 and res.json()["code"] == "AI_COOLDOWN"
    assert 0 < res.json()["params"]["seconds"] <= 60 and res.headers["Retry-After"]
    assert fake_groq["calls"] == 1


# ===== 8. TWO REQUESTS AT THE SAME TIME =====
def test_simultaneous_requests_make_one_call(new_client, sent_codes, fake_groq):
    first = log_in(new_client(), sent_codes)
    add_month_data(first)
    second = new_client()
    second.cookies.update(first.cookies)  # same user, second browser tab
    fake_groq["delay"] = 0.5
    results = []
    threads = [threading.Thread(target=lambda c=c: results.append(generate(c))) for c in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert fake_groq["calls"] == 1
    assert sorted(res.status_code for res in results) == [200, 200]
    assert sorted(res.json()["cached"] for res in results) == [False, True]


# ===== 9. DAILY LIMIT =====
def test_daily_limit(user, fake_groq, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "2")
    monkeypatch.setenv("AI_COOLDOWN_SECONDS", "0")
    for amount in (1000, 2000):
        assert generate(user).json()["cached"] is False
        user.post("/api/expenses", json={"amount": amount, "category": "Other", "date": TODAY})
    res = generate(user)
    assert res.status_code == 429 and res.json()["code"] == "AI_DAILY_LIMIT" and res.json()["params"]["limit"] == 2
    assert fake_groq["calls"] == 2
    body = user.get(f"/api/insights?month={MONTH}").json()  # the maths + the last analysis still work
    assert body["analysis"]["take_home_income"] == 20000 and body["saved"]["insight"]


# ===== 10. GROQ ERRORS AND 429 =====
def test_groq_error_saves_nothing_and_is_not_retried(user, fake_groq):
    fake_groq["reply"] = AiUnavailable("AI_FAILED")
    res = generate(user)
    assert res.status_code == 502 and res.json()["code"] == "AI_FAILED"
    assert fake_groq["calls"] == 1  # one try, no automatic retries
    assert user.get(f"/api/insights?month={MONTH}").json()["saved"]["status"] == "none"


def test_bad_ai_reply_is_rejected(user, fake_groq):
    for reply in ("not json", '{"overview": "only this"}', '["a list"]',
                  '{"overview": "x", "observations": [], "suggestions": [{"title": "t"}], '
                  '"savings_analysis": "", "encouragement": ""}'):
        fake_groq["reply"] = reply
        forget_cooldown()
        res = generate(user)
        assert res.status_code == 502 and res.json()["code"] == "AI_BAD_RESPONSE"
    assert user.get(f"/api/insights?month={MONTH}").json()["saved"]["insight"] is None


def test_groq_429_pauses_all_calls(user, fake_groq, monkeypatch):
    monkeypatch.setenv("AI_COOLDOWN_SECONDS", "0")
    fake_groq["reply"] = AiUnavailable("AI_RATE_LIMITED", 30)
    res = generate(user)
    assert res.status_code == 503 and res.json()["code"] == "AI_RATE_LIMITED"
    assert res.headers["Retry-After"] == "30"
    res = generate(user)  # still paused: Groq is not called again
    assert res.status_code == 503 and fake_groq["calls"] == 1
    assert user.get(f"/api/insights?month={MONTH}").json()["paused_seconds"] > 0


def test_real_sender_reads_429_and_timeouts(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(429, headers={"retry-after": "30"}))
    with pytest.raises(AiUnavailable) as problem:
        send_to_groq([], settings)
    assert problem.value.code == "AI_RATE_LIMITED" and problem.value.retry_after == 30

    def too_slow(*args, **kwargs):
        raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(httpx, "post", too_slow)
    with pytest.raises(AiUnavailable) as problem:
        send_to_groq([], settings)
    assert problem.value.code == "AI_TIMEOUT"

    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        200, json={"choices": [{"message": {"content": '{"a": 1}'}}]}))
    assert send_to_groq([], settings) == '{"a": 1}'


# ===== 11. NO GROQ AT ALL =====
def test_app_works_without_a_groq_key(user, fake_groq, monkeypatch):
    generate(user)  # an older analysis exists
    monkeypatch.setenv("GROQ_API_KEY", "")
    user.post("/api/expenses", json={"amount": 3000, "category": "Other", "date": TODAY})
    body = user.get(f"/api/insights?month={MONTH}").json()
    assert body["ai_configured"] is False and body["analysis"]["needs"] == 11000
    assert body["saved"]["status"] == "outdated" and body["saved"]["insight"]  # last analysis still visible
    res = generate(user)
    assert res.status_code == 503 and res.json()["code"] == "AI_NOT_CONFIGURED"
    assert fake_groq["calls"] == 1


# ===== 12. OTHER USERS =====
def test_one_user_cannot_see_another_users_analysis(new_client, sent_codes, fake_groq):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    add_month_data(asha)
    assert generate(asha).status_code == 200
    ravi = log_in(new_client(), sent_codes, "ravi@example.com")
    body = ravi.get(f"/api/insights?month={MONTH}").json()
    assert body["saved"]["status"] == "none" and body["analysis"]["take_home_income"] is None
    assert body["usage"]["used_today"] == 0


def test_insights_need_login(client):
    assert client.get("/api/insights").status_code == 401
    assert client.post("/api/insights/generate", json={}).status_code == 401


# ===== 13. QUICK INSIGHTS (no AI) + GOALS WITHOUT A MONTHLY PLAN =====
def quick(client):
    return client.post("/api/insights/quick", json={"month": MONTH})


def quick_codes(client):
    res = quick(client)
    assert res.status_code == 200
    return {tip["code"]: tip["params"] for tip in res.json()["quick"]}


def test_quick_insights_without_a_key_never_call_groq(user, fake_groq, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert user.get(f"/api/insights?month={MONTH}").json()["ai_configured"] is False
    codes = quick_codes(user)
    assert codes["TOP_CATEGORY"] == {"category": "Groceries", "amount": 8000, "percent": 67}
    assert codes["GOAL_PLAN"]["name"] == "Private laptop" and codes["GOAL_PLAN"]["amount"] > 0
    assert any(c == "SPLIT" for c in codes) and fake_groq["calls"] == 0


@pytest.mark.parametrize("problem", ["AI_FAILED", "AI_TIMEOUT"])
def test_quick_insights_still_work_after_ai_failure_or_timeout(user, fake_groq, problem):
    fake_groq["reply"] = AiUnavailable(problem)
    res = generate(user)
    assert res.status_code == 502 and res.json()["code"] == problem
    assert "TOP_CATEGORY" in quick_codes(user) and fake_groq["calls"] == 1  # the quick ones never call Groq


def test_quick_insights_with_no_data_point_to_the_right_place(logged_in, fake_groq):
    codes = quick_codes(logged_in)
    assert "ADD_INCOME" in codes and "ADD_EXPENSES" in codes and fake_groq["calls"] == 0


def test_quick_insights_loan_share(user):
    assert user.post("/api/my-loans", json={"balance": 50000, "annual_rate": 10, "monthly_payment": 2000}).status_code == 201
    assert quick_codes(user)["LOAN_SHARE"] == {"amount": 2000, "percent": 10}


def test_past_deadline_goal_has_no_monthly_amount_and_does_not_crash(user):
    assert user.post("/api/goals", json={"name": "car", "target_amount": 100000, "deadline": "2020-01-01"}).status_code == 201
    goals = {g["name"]: g for g in user.get("/api/goals").json()["goals"]}
    assert goals["car"]["needs_per_month"] is None and goals["car"]["plan"] == "deadline_passed"
    body = user.get(f"/api/insights?month={MONTH}").json()
    car = [g for g in body["analysis"]["goals"] if g["name"] == "car"][0]
    assert car["needs_per_month"] is None and car["months_left"] is None
    assert quick_codes(user)["GOAL_LATE"]["name"] == "car"
    assert user.get(f"/api/dashboard?today={TODAY}").status_code == 200


def test_goal_without_target_or_deadline_gets_no_monthly_amount():
    from money import get_goal_statuses, get_needs_per_month
    base = {"id": "1", "name": "car", "saved_amount": 500, "priority": 2, "created_at": "2026-01-01"}
    no_target = {**base, "target_amount": None, "deadline": "2030-01-01"}
    no_date = {**base, "target_amount": 100000, "deadline": None}
    assert get_needs_per_month(no_target, TODAY) is None and get_needs_per_month(no_date, TODAY) is None
    rows = get_goal_statuses([no_target, no_date], 5000, TODAY)
    assert [(r["needs_per_month"], r["plan"], r["status"]) for r in rows] == [(None, "no_plan", "No target")] * 2
