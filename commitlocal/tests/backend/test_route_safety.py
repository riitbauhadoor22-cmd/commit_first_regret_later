# test_route_safety.py — goes through EVERY /api route of the app (read from main.app, not a hand-written list):
# protected routes give 401 when not logged in, and no route gives a 500 for empty, negative, huge or text input.
import uuid

import pytest
from fastapi.routing import APIRoute

import main

PUBLIC = {"/api/auth/register", "/api/auth/login", "/api/auth/resend-code", "/api/auth/send-login-code",
          "/api/auth/verify-code", "/api/auth/logout"}
BAD_VALUES = [None, "", "abc", -5, 0, 1e20, -1e20, [], {}]


def api_routes():
    """Every (method, path, route) the app answers under /api."""
    found = []

    def walk(routes):
        for route in routes:
            if isinstance(route, APIRoute) and route.path.startswith("/api/"):
                found.extend((method, route.path, route) for method in sorted(route.methods))
            inner = getattr(route, "original_router", None)  # newer FastAPI wraps included routers
            if inner is not None:
                walk(inner.routes)

    walk(main.app.routes)
    return found


def fill_path(path, value):
    return (path.replace("{expense_id}", value).replace("{income_id}", value).replace("{goal_id}", value)
            .replace("{attempt_id}", value).replace("{loan_id}", value))


def body_fields(route):
    """Names of the JSON body fields this route reads (empty list if it has no body)."""
    if route.body_field is None:
        return []
    return list(route.body_field.field_info.annotation.model_fields)


ROUTES = api_routes()
PROTECTED = [(m, p) for m, p, _ in ROUTES if p not in PUBLIC and p != "/api/auth/me"] + [("GET", "/api/auth/me")]


def test_routes_were_found():  # sanity: the app really has the money routes
    paths = {p for _, p, _ in ROUTES}
    assert {"/api/summary", "/api/expenses", "/api/income", "/api/budgets", "/api/goals", "/api/savings",
            "/api/loans/predict", "/api/auth/language",
            "/api/game/levels", "/api/game/attempts", "/api/game/attempts/{attempt_id}/submit"} <= paths


@pytest.mark.parametrize("method, path", PROTECTED)
def test_protected_route_needs_login(client, method, path):  # not logged in -> 401 on every protected route
    res = client.request(method, fill_path(path, str(uuid.uuid4())), json={})
    assert res.status_code == 401, f"{method} {path} gave {res.status_code}"


@pytest.mark.parametrize("method, path, route", ROUTES)
def test_no_500_on_bad_input(logged_in, method, path, route):  # bad values in every field -> 4xx, never 500
    url = fill_path(path, str(uuid.uuid4()))
    fields = body_fields(route)
    bodies = [{}, None] + [{name: bad for name in fields} for bad in BAD_VALUES]
    for name in fields:  # one bad field at a time too
        bodies += [{name: bad} for bad in (-5, 1e20, "abc")]
    for body in bodies:
        res = logged_in.request(method, url, json=body)
        assert res.status_code < 500, f"{method} {path} body={body} gave {res.status_code}"
    if "{" in path:  # a non-UUID id -> 422, not 500
        assert logged_in.request(method, fill_path(path, "abc"), json={}).status_code < 500
    if method == "GET":
        for month in ("abc", "2026-13", "9999-99", ""):
            assert logged_in.get(url, params={"month": month}).status_code < 500


@pytest.mark.parametrize("path", ["/api/expenses", "/api/income/" + str(uuid.uuid4()), "/api/goals"])
def test_text_body_is_rejected(logged_in, path):  # a body that isn't JSON at all -> 4xx, not 500
    method = "PUT" if "income/" in path else "POST"
    res = logged_in.request(method, path, content=b"hello", headers={"Content-Type": "application/json"})
    assert 400 <= res.status_code < 500


@pytest.mark.parametrize("number", ["1e20", "-1e20", "Infinity", "-Infinity", "NaN"])
def test_huge_or_not_finite_numbers_give_422(logged_in, number):  # 1e20 / Infinity / NaN -> 422 (was 500 for Infinity/NaN)
    json_header = {"Content-Type": "application/json"}
    expense = logged_in.post("/api/expenses", content=f'{{"amount": {number}, "category": "Other"}}', headers=json_header)
    assert expense.status_code == 422
    loan = logged_in.post("/api/loans/predict", headers=json_header,
                          content=f'{{"monthly_income": {number}}}')
    assert loan.status_code == 422
    assert logged_in.put("/api/savings", content=f'{{"bank_balance": {number}}}', headers=json_header).status_code == 422
