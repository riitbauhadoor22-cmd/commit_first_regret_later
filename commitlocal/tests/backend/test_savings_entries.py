# test_savings_entries.py — real savings: "Add to savings" / "Take out" entries move total savings (bank balance)
# and the safety net / goal picked; saved this month = put in − taken out; editing or deleting undoes the effect;
# "Update total savings" (starting balance) is never saved this month; one user can't touch another's entries.
from conftest import log_in
from money import get_this_month

ENTRIES = "/api/savings/entries"


def entry(client, kind="deposit", amount=1000, place="general", **extra):
    return client.post(ENTRIES, json={"kind": kind, "amount": amount, "place": place, **extra})


def savings(client):
    return client.get("/api/savings").json()


def new_goal(client, target=5000):
    assert client.post("/api/goals", json={"name": "Bike", "target_amount": target, "deadline": "2028-01-01",
                                           "priority": 1}).status_code == 201
    return client.get("/api/goals").json()["goals"][0]["id"]


def test_deposit_raises_total_and_saved_this_month(logged_in):
    assert logged_in.put("/api/savings", json={"bank_balance": 10000}).status_code == 200
    assert savings(logged_in)["saved_this_month"] == 0  # the starting balance is not saved this month
    data = entry(logged_in, amount=1500).json()
    assert data["bank_balance"] == 11500 and data["saved_this_month"] == 1500
    assert logged_in.get("/api/summary").json()["saved"] == 1500


def test_deposit_and_take_out_of_safety_net_and_goal(logged_in):
    goal_id = new_goal(logged_in)
    entry(logged_in, amount=2000, place="safety_net")
    data = entry(logged_in, amount=3000, place="goal", goal_id=goal_id).json()
    assert data["bank_balance"] == 5000 and data["safety_net"]["saved"] == 2000
    assert logged_in.get("/api/goals").json()["goals"][0]["saved_amount"] == 3000
    data = entry(logged_in, "withdrawal", 500, "safety_net").json()
    assert data["bank_balance"] == 4500 and data["safety_net"]["saved"] == 1500
    assert data["saved_this_month"] == 4500  # 2,000 + 3,000 − 500
    data = entry(logged_in, "withdrawal", 1000, "goal", goal_id=goal_id).json()
    assert logged_in.get("/api/goals").json()["goals"][0]["saved_amount"] == 2000 and data["bank_balance"] == 3500


def test_cant_take_out_more_than_there_is(logged_in):
    entry(logged_in, amount=1000, place="safety_net")
    for place in ("safety_net", "general"):
        res = entry(logged_in, "withdrawal", 5000, place)
        assert res.status_code == 400 and res.json()["code"] == "NOT_ENOUGH_SAVINGS"
    assert savings(logged_in)["bank_balance"] == 1000  # nothing changed


def test_goal_rules(logged_in):
    goal_id = new_goal(logged_in, target=1000)
    res = entry(logged_in, amount=1500, place="goal", goal_id=goal_id)
    assert res.status_code == 400 and res.json()["code"] == "MORE_THAN_GOAL_NEEDS" and res.json()["params"]["left"] == 1000
    assert entry(logged_in, place="goal").json()["code"] == "GOAL_REQUIRED"


def test_edit_and_delete_undo_the_effect(logged_in):
    first = entry(logged_in, amount=1000, place="safety_net").json()["entry"]
    data = logged_in.put(f"{ENTRIES}/{first['id']}", json={"kind": "deposit", "amount": 400, "place": "general"}).json()
    assert data["bank_balance"] == 400 and data["safety_net"]["saved"] == 0 and data["saved_this_month"] == 400
    data = logged_in.delete(f"{ENTRIES}/{data['entry']['id']}").json()
    assert data["bank_balance"] == 0 and data["saved_this_month"] == 0
    assert logged_in.get(ENTRIES).json()["entries"] == []


def test_undo_that_would_go_below_zero_is_refused(logged_in):
    first = entry(logged_in, amount=1000).json()["entry"]
    entry(logged_in, "withdrawal", 800)
    res = logged_in.delete(f"{ENTRIES}/{first['id']}")  # removing the deposit would leave −800
    assert res.status_code == 400 and res.json()["code"] == "NOT_ENOUGH_SAVINGS"
    assert savings(logged_in)["bank_balance"] == 200


def test_more_taken_out_than_put_in_this_month(logged_in):
    assert logged_in.put("/api/savings", json={"bank_balance": 5000}).status_code == 200
    entry(logged_in, "withdrawal", 1200)
    assert savings(logged_in)["saved_this_month"] == -1200


def test_entries_by_month_and_owner(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes)
    bob = log_in(new_client(), sent_codes, "bob@example.com")
    entry(asha, amount=100, date="2026-01-15")
    mine = entry(asha, amount=200).json()["entry"]
    listed = asha.get(ENTRIES, params={"month": get_this_month()}).json()["entries"]
    assert [e["amount"] for e in listed] == [200]
    assert bob.delete(f"{ENTRIES}/{mine['id']}").json()["code"] == "ENTRY_NOT_FOUND"
    assert bob.get(ENTRIES).json()["entries"] == []


def test_general_take_out_only_uses_free_money(logged_in):
    goal_id = new_goal(logged_in)
    entry(logged_in, amount=1000)                                    # free money
    entry(logged_in, amount=2000, place="goal", goal_id=goal_id)     # set aside for the goal
    entry(logged_in, amount=500, place="safety_net")                 # set aside in the safety net
    res = entry(logged_in, "withdrawal", 1200)                       # only 1,000 is free
    assert res.status_code == 400 and res.json()["code"] == "SET_ASIDE_FOR_GOALS"
    assert res.json()["params"]["available"] == 1000
    assert entry(logged_in, "withdrawal", 1000).status_code == 201  # all the free money is fine
    assert entry(logged_in, "withdrawal", 300, place="goal", goal_id=goal_id).status_code == 201  # from the goal
    assert savings(logged_in)["bank_balance"] == 2200
