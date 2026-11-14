# test_categorise.py — auto-categorise expenses (category_keywords.py + GET /api/expenses/suggest-category):
# keywords, case/accents, the user's own history beating keywords, other users' history ignored, no match.
from categories import CATEGORIES
from category_keywords import CATEGORY_KEYWORDS, match_keywords, normalise, suggest_category
from conftest import log_in


# ===== KEYWORDS =====
def test_keyword_list_uses_real_categories():
    assert set(CATEGORY_KEYWORDS) <= set(CATEGORIES)


def test_keywords_find_the_category():
    assert match_keywords("KFC 350") == "Food & drinks"
    assert match_keywords("Winners groceries") == "Groceries"
    assert match_keywords("Metro Express to Rose-Hill") == "Transport"
    assert match_keywords("my.t internet") == "Subscriptions"
    assert match_keywords("McDonald's with friends") == "Food & drinks"


def test_case_accents_and_whole_words():
    assert normalise("Dholl Purî") == "dholl puri"
    assert match_keywords("DHOLL PURÎ x2") == "Food & drinks"
    assert match_keywords("mcdonalds") == "Food & drinks"
    assert match_keywords("CÉB bill") == "Utilities"
    assert match_keywords("busy day") is None       # "bus" only as a whole word
    assert match_keywords("gasoline") is None


def test_no_match_gives_nothing():
    assert suggest_category("something random 120", []) == {"category": None, "source": None}
    assert suggest_category("", []) == {"category": None, "source": None}


# ===== HISTORY =====
def past(note, category, day="2026-11-01"):
    return {"note": note, "category": category, "date": day}


def test_history_beats_keywords():
    history = [past("Emtel top up", "Bills"), past("emtel", "Bills"), past("Emtel", "Subscriptions")]
    assert suggest_category("EMTEL 500", history) == {"category": "Bills", "source": "history"}
    assert suggest_category("Emtel 500", []) == {"category": "Subscriptions", "source": "keywords"}


def test_history_ignores_numbers_and_filler_words():
    history = [past("350", "Bills"), past("for mum", "Other")]
    assert suggest_category("KFC 350 for", history)["source"] == "keywords"


def test_route_uses_only_my_history(new_client, sent_codes):
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    ben = log_in(new_client(), sent_codes, "ben@example.com")
    asha.post("/api/expenses", json={"amount": 99, "category": "Shopping", "note": "KFC voucher"})
    assert asha.get("/api/expenses/suggest-category", params={"text": "kfc 350"}).json() == {
        "category": "Shopping", "source": "history"}
    assert ben.get("/api/expenses/suggest-category", params={"text": "kfc 350"}).json() == {
        "category": "Food & drinks", "source": "keywords"}
    assert ben.get("/api/expenses/category-keywords").json()["keywords"]["Groceries"][0] == "Winners"


def test_new_routes_need_login(client):
    for path in ("/api/expenses/suggest-category?text=kfc", "/api/expenses/category-keywords", "/api/forecast"):
        assert client.get(path).status_code == 401
