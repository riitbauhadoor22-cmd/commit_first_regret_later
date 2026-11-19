# test_game.py — Arcade "Budget Challenge": server scoring (spec cases: exact income, unallocated, over income,
# no savings, needs > 50%, wants > 30%, essentials, cost / discount / bonus events), locked values, events off,
# XP once per attempt + replay, +20 first-completion bonus once per level, per user, 401, money tables untouched.
import uuid

import pytest
from sqlalchemy import func, select

import database
from conftest import log_in
from game import scenarios
from game.scenarios import get_event, get_level
from game.scoring import allocation_points, score_allocation
from models import Budget, Expense, Income

L1, L3 = get_level(1), get_level(3)


def perfect_l1():
    """Rs 15,000: Needs 7,500 (50%), Wants 4,500 (30%), Savings 3,000 (20%), every minimum met."""
    return {"food": 4000, "transport": 1800, "phone": 800, "study": 900, "entertainment": 2500, "personal": 2000,
            "savings": 3000}


def score(level, rupees, event=None, applied=True):
    cents = {c["id"]: round(rupees.get(c["id"], 0) * 100) for c in level["categories"]}
    return score_allocation(level, cents, event, event_applied=applied)


def points(result):
    return {item["key"]: item["points"] for item in result["breakdown"]}


def codes(result):
    return [tip["code"] for tip in result["tips"]]


# ===== PURE SCORING (spec cases) =====
def test_exact_full_income_scores_100():
    result = score(L1, perfect_l1())
    assert result["score"] == 100 and result["left"] == 0
    assert codes(result)[0] == "balanced" and "great" in codes(result)


def test_some_unallocated_is_a_buffer_then_costs_points():
    small = score(L1, dict(perfect_l1(), savings=2000))  # Rs 1,000 left = 6.7% -> sensible buffer
    assert points(small)["balance"] == 30 and "unassigned" in codes(small)
    big = score(L1, dict(perfect_l1(), savings=0, personal=0))  # Rs 5,000 left = 33%
    assert points(big)["balance"] == 20


def test_balance_threshold_at_10_percent_unallocated():
    assert points(score(L1, dict(perfect_l1(), savings=1500)))["balance"] == 30  # exactly 10% left
    assert points(score(L1, dict(perfect_l1(), savings=1499.99)))["balance"] == 20  # just over 10%


def test_exceeds_income_gets_no_balance_points():
    result = score(L1, dict(perfect_l1(), personal=2001))
    assert points(result)["balance"] == 0 and "overspend" in codes(result)


def test_nothing_to_savings():
    result = score(L1, dict(perfect_l1(), savings=0, entertainment=5500))
    assert points(result)["savings"] == 0 and "no_savings" in codes(result)
    assert points(result)["allocation"] == 14  # needs 7 + wants 50% (half: 3.5) + savings 0% (half: 3) = 13.5 -> 14


def test_savings_not_rewarded_above_goal():
    goal = score(L1, dict(perfect_l1(), savings=1500, personal=3500))  # exactly 10% of income
    more = score(L1, perfect_l1())
    assert points(goal)["savings"] == points(more)["savings"] == 15


@pytest.mark.parametrize("saved,expected", [(0, 0), (150, 10), (750, 10), (1499.99, 10), (1500, 15), (3750, 15)])
def test_savings_thresholds(saved, expected):  # 0% · 1% · 5% · just under 10% · 10% · 25% of Rs 15,000
    assert points(score(L1, dict(perfect_l1(), savings=saved)))["savings"] == expected


@pytest.mark.parametrize("kind,share", [("need", 7), ("want", 7), ("savings", 6)])
def test_allocation_group_thresholds(kind, share):
    def pts(gap):
        percents = {"need": 50, "want": 30, "savings": 20}
        percents[kind] += gap
        return allocation_points(percents)
    for sign in (1, -1):
        assert pts(sign * 10) == 20  # within ±10 points: full share
        assert pts(sign * 10.01) == pts(sign * 20) == round(20 - share / 2 + 0.01)  # within ±20: half (16.5 -> 17)
        assert pts(sign * 20.01) == 20 - share  # beyond ±20: 0


def test_allocation_halves_round_half_up():
    assert allocation_points({"need": 65, "want": 30, "savings": 20}) == 17  # 3.5 + 7 + 6 = 16.5
    assert allocation_points({"need": 65, "want": 15, "savings": 20}) == 13  # 3.5 + 3.5 + 6
    assert allocation_points({"need": 100, "want": 0, "savings": 0}) == 3  # only savings (20 off) gets half


def test_needs_above_50_percent():
    slightly = score(L1, dict(perfect_l1(), food=4750, personal=1250))  # needs 55%, wants 25%
    assert points(slightly)["allocation"] == 20 and "high_needs_ok" in codes(slightly)
    edge = score(L1, dict(perfect_l1(), food=5500, personal=500))  # needs 60%, wants 20%: both still within ±10
    assert points(edge)["allocation"] == 20 and "high_needs_ok" in codes(edge)
    much = score(L1, dict(perfect_l1(), food=6250, personal=0, entertainment=2250))  # needs 65%, wants 15% -> halves
    assert points(much)["allocation"] == 13 and "needs_high" in codes(much)


def test_wants_above_30_percent():
    result = score(L1, dict(perfect_l1(), entertainment=4000, savings=1500))  # wants 40%, savings 10%
    assert points(result)["allocation"] == 20 and "large_wants" in codes(result)  # both exactly 10 points off: full


def test_essentials_coverage():
    assert points(score(L1, perfect_l1()))["essentials"] == 25
    one_short = score(L1, dict(perfect_l1(), transport=1499.99, savings=3300.01))
    assert points(one_short)["essentials"] == 19  # 3 of 4 covered
    assert {"code": "essential_short", "params": {"category": "transport", "min": 1500}} in one_short["tips"]
    assert points(one_short)["savings"] == 15 and "save_vs_essentials" in codes(one_short)  # tip only, no cap
    two_short = score(L1, dict(perfect_l1(), transport=0, phone=0))
    assert points(two_short)["essentials"] == 13  # 2 of 4 -> 12.5, rounded half up
    assert points(score(L1, dict(perfect_l1(), food=0, transport=0, phone=0, study=0)))["essentials"] == 0
    l3 = {"rent": 12000, "groceries": 5000, "electricity_water": 2000, "transport": 2000, "phone": 0, "healthcare": 700}
    assert points(score(L3, l3))["essentials"] == 20  # 4 of 5 min_amount essentials (locked rent / loan don't count)


def test_high_rent_level_3_can_reach_100():
    sensible = {"rent": 12000, "groceries": 5000, "electricity_water": 2000, "transport": 2000, "phone": 800,
                "healthcare": 700, "entertainment": 7000, "personal": 6500, "savings": 6000, "loan": 3000}
    assert score(L3, sensible)["score"] == 100


def test_events_off_automatic_and_pending_event():
    assert points(score(L1, perfect_l1(), None))["events"] == 10
    preview = score(L1, perfect_l1(), get_event(L1, "charger"), applied=False)
    assert points(preview)["events"] is None and preview["score"] == 90


def test_unexpected_expense():
    event = get_event(L1, "bus_fare")  # transport +500 -> needs 2,000
    missed = score(L1, perfect_l1(), event)
    assert points(missed)["events"] == 0 and "event_failed" in codes(missed)
    assert missed["score"] == 90  # a missed cost event only loses its own 10 points
    adapted = score(L1, dict(perfect_l1(), transport=2300, personal=1500), event)
    assert points(adapted)["events"] == 10 and "event_handled" in codes(adapted)


def test_discount_lowers_minimum():
    event = get_event(L1, "grocery_discount")  # food needs Rs 300 less
    result = score(L1, dict(perfect_l1(), food=3700, savings=3300), event)
    assert points(result)["essentials"] == 25 and points(result)["events"] == 10


def test_bonus_adds_income():
    result = score(L1, perfect_l1(), get_event(L1, "small_bonus"))  # +Rs 1,000
    assert result["income"] == 16000 and result["left"] == 1000 and points(result)["events"] == 10


def test_config_is_consistent():
    for level in scenarios.LEVELS:
        ids = [c["id"] for c in level["categories"]]
        assert len(ids) == len(set(ids)) and 5 <= len(ids) <= 10 and "savings" in ids
        biggest_cost = max([e["amount"] for e in level["events"] if e["type"] == "cost"] + [0])
        assert sum(scenarios.minimum_of(c) for c in level["categories"]) + biggest_cost <= level["income"]  # never forced negative
        assert all(e["category"] in ids for e in level["events"])
        # all minimums + locked amounts fit in 85% of income
        assert sum(scenarios.minimum_of(c) for c in level["categories"]) * 100 <= level["income"] * scenarios.MIN_SHARE_MAX
    assert [c["id"] for c in L1["categories"] if "locked" in c] == []
    assert {c["id"]: (c["locked"], c["kind"]) for c in get_level(2)["categories"] if "locked" in c} == {"loan": (2500, "savings")}
    assert {c["id"]: c["locked"] for c in L3["categories"] if "locked" in c} == {"rent": 12000, "loan": 3000}


# ===== API =====
def start(client, level=1, events_on=False):
    res = client.post("/api/game/attempts", json={"level": level, "events_on": events_on})
    assert res.status_code == 201
    return res.json()


def submit(client, attempt_id, allocation, final=True):
    return client.post(f"/api/game/attempts/{attempt_id}/submit", json={"allocation": allocation, "final": final})


def test_logged_out_gets_401(client):
    assert client.get("/api/game/levels").status_code == 401
    assert client.post("/api/game/attempts", json={"level": 1}).status_code == 401
    assert client.get("/api/game/attempts").status_code == 401


def test_over_income_is_rejected(logged_in):
    game = start(logged_in)
    res = submit(logged_in, game["attempt_id"], dict(perfect_l1(), savings=3001))
    assert res.status_code == 400 and res.json()["code"] == "GAME_OVER_INCOME"


def test_complete_replay_and_no_duplicate_xp(logged_in):
    game = start(logged_in)
    first = submit(logged_in, game["attempt_id"], perfect_l1()).json()
    assert first["score"] == 100 and first["xp_awarded"] == 120 and first["first_completion_bonus"] is True
    again = submit(logged_in, game["attempt_id"], perfect_l1()).json()  # repeat submit -> no XP
    assert again["xp_awarded"] == 0 and again["already_completed"] is True and again["score"] == 100
    replay = submit(logged_in, start(logged_in)["attempt_id"], perfect_l1()).json()  # replay same level
    assert replay["xp_awarded"] == 100 and replay["first_completion_bonus"] is False
    history = logged_in.get("/api/game/attempts").json()
    assert history["total_xp"] == 220 and len(history["attempts"]) == 2 and history["best_scores"] == {"1": 100}


def test_event_flow_reveal_then_one_adjustment(logged_in):
    game = start(logged_in, level=1, events_on=True)
    assert game["has_event"] is True and "event" not in game  # secret until the first submit
    early = submit(logged_in, game["attempt_id"], perfect_l1(), final=True)
    assert early.status_code == 400 and early.json()["code"] == "GAME_EVENT_PENDING"
    first = submit(logged_in, game["attempt_id"], perfect_l1(), final=False).json()
    assert first["stage"] == "event" and first["event"]["id"] and first["xp_awarded"] == 0
    assert submit(logged_in, game["attempt_id"], perfect_l1(), final=False).json()["code"] == "GAME_FINAL_NEEDED"
    slack = dict(perfect_l1(), savings=2000)  # Rs 1,000 left covers any cost event (max +500)
    final = submit(logged_in, game["attempt_id"], slack, final=True).json()
    assert final["stage"] == "done" and final["xp_awarded"] == final["score"] + 20


def start_with_event(client, monkeypatch, event_id, level=1):
    monkeypatch.setattr("routes.game.choose_event", lambda lvl, on: get_event(lvl, event_id))
    return start(client, level=level, events_on=True)


def test_shortfall_when_event_pushes_over_income(logged_in, monkeypatch):
    game = start_with_event(logged_in, monkeypatch, "bus_fare")  # transport needs +500
    first = submit(logged_in, game["attempt_id"], perfect_l1(), final=False).json()  # transport 1,800 < 2,000
    assert first["stage"] == "event" and first["shortfall"] == 200
    # Over income: blocked as often as needed, nothing used up
    for _ in range(3):
        blocked = submit(logged_in, game["attempt_id"], dict(perfect_l1(), transport=2000), final=True)
        assert blocked.status_code == 400 and blocked.json()["code"] == "GAME_OVER_INCOME"
        short = submit(logged_in, game["attempt_id"], perfect_l1(), final=True)  # unchanged: event not covered
        assert short.status_code == 400 and short.json()["code"] == "GAME_EVENT_SHORTFALL"
        assert short.json()["params"] == {"short": 200}
    assert submit(logged_in, game["attempt_id"], perfect_l1(), final=False).json()["code"] == "GAME_FINAL_NEEDED"
    final = submit(logged_in, game["attempt_id"], dict(perfect_l1(), transport=2000, personal=1800), final=True).json()
    assert final["stage"] == "done" and final["score"] == 100 and final["xp_awarded"] == 120


def test_no_shortfall_when_event_fits(logged_in, monkeypatch):
    game = start_with_event(logged_in, monkeypatch, "bus_fare")
    fine = dict(perfect_l1(), savings=2500)  # Rs 500 left covers the +500
    assert submit(logged_in, game["attempt_id"], fine, final=False).json()["shortfall"] == 0
    game = start_with_event(logged_in, monkeypatch, "small_bonus")
    assert submit(logged_in, game["attempt_id"], perfect_l1(), final=False).json()["shortfall"] == 0


def test_unknown_attempt_id_is_404(logged_in):
    res = submit(logged_in, uuid.uuid4(), perfect_l1())
    assert res.status_code == 404 and res.json()["code"] == "GAME_NOT_FOUND"


def test_events_can_be_turned_off_on_every_level(logged_in):
    for level in (1, 2, 3):
        assert start(logged_in, level=level, events_on=False)["has_event"] is False


def test_locked_values_and_categories_enforced(logged_in):
    game = start(logged_in, level=2)
    good = {"loan": 2500, "rent_household": 6500, "groceries": 4000}
    changed = submit(logged_in, game["attempt_id"], dict(good, loan=1000), final=False)
    assert changed.status_code == 400 and changed.json()["code"] == "GAME_LOCKED_CHANGED"
    assert submit(logged_in, game["attempt_id"], {"groceries": 100}, final=False).json()["code"] == "GAME_LOCKED_CHANGED"
    assert submit(logged_in, game["attempt_id"], dict(good, rent=100), final=False).json()["code"] == "GAME_UNKNOWN_CATEGORY"
    assert submit(logged_in, game["attempt_id"], good, final=False).status_code == 200


@pytest.mark.parametrize("bad", [-1, 1e20, "abc", None])
def test_bad_amounts_rejected(logged_in, bad):
    assert submit(logged_in, start(logged_in)["attempt_id"], {"food": bad}).status_code == 422


def test_nan_amount_rejected(logged_in):
    game = start(logged_in)
    res = logged_in.post(f"/api/game/attempts/{game['attempt_id']}/submit", content='{"allocation": {"food": NaN}}',
                         headers={"Content-Type": "application/json"})
    assert res.status_code == 422


def test_decimal_amounts_kept_in_cents(logged_in):
    game = start(logged_in)
    result = submit(logged_in, game["attempt_id"], dict(perfect_l1(), savings=2999.99)).json()
    assert result["left"] == 0.01 and result["total"] == 14999.99


def test_unknown_level(logged_in):
    assert logged_in.post("/api/game/attempts", json={"level": 9}).json()["code"] == "GAME_LEVEL_NOT_FOUND"
    assert logged_in.post("/api/game/attempts", json={"level": 0}).status_code == 422


def test_attempts_are_per_user(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    ravi = log_in(new_client(), sent_codes, "ravi@example.com")
    game = start(asha)
    assert submit(ravi, game["attempt_id"], perfect_l1()).status_code == 404  # can't play someone else's game
    submit(asha, game["attempt_id"], perfect_l1())
    assert ravi.get("/api/game/attempts").json() == {"attempts": [], "total_xp": 0, "best_scores": {}}
    assert asha.get("/api/game/attempts").json()["total_xp"] == 120


def test_game_never_touches_money_tables(logged_in):
    def counts():
        with database.open_db() as db:
            return [db.scalar(select(func.count()).select_from(t)) for t in (Income, Expense, Budget)]
    before = counts()
    for level in (1, 2, 3):
        game = start(logged_in, level=level, events_on=True)
        alloc = {c["id"]: c.get("locked", c.get("min_amount", 100)) for c in game["level"]["categories"]}
        submit(logged_in, game["attempt_id"], alloc, final=False)
        submit(logged_in, game["attempt_id"], alloc, final=True)
    assert counts() == before == [0, 0, 0]
