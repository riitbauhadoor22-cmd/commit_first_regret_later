# category_keywords.py — guesses an expense's category from its note (e.g. "KFC 350" → "Food & drinks").
# No AI, no internet. Order: (1) the user's own history (the category they used most for a note with the same
# word), (2) the Mauritian keyword list below, (3) no match → None (the form is left as it is).
# The keyword list is the ONE place to edit: the frontend downloads it (GET /api/expenses/category-keywords)
# and keeps a copy on the phone, so guessing also works offline (category-guess.js).
import re
import unicodedata
from collections import Counter

from categories import CATEGORIES

# ===== KEYWORD LIST (edit here) =====
# Keys must be categories from categories.py. Matching ignores case, accents and punctuation, whole words only.
CATEGORY_KEYWORDS = {
    "Groceries": ["Winners", "Intermart", "Super U", "Jumbo", "Dreamprice", "Spar", "bazar"],
    "Food & drinks": ["KFC", "McDonald's", "Pizza Hut", "dholl puri", "roti", "snack"],
    "Transport": ["bus", "taxi", "metro", "Metro Express", "essence", "petrol", "parking"],
    "Utilities": ["CEB", "CWA", "gas"],
    "Subscriptions": ["Emtel", "my.t", "MTML", "Netflix", "Spotify"],
    "Shopping": ["Courts", "Galaxy", "clothes", "shoes"],
    "Fun & outings": ["cinema", "MCine", "bowling", "concert"],
}

# Little words that say nothing about the category (they are ignored when looking at the user's history)
SKIP_WORDS = {"the", "and", "for", "with", "from", "pour", "avec", "les", "des", "une", "pou", "enn", "ek", "bann"}
MIN_WORD_LENGTH = 2


# ===== MATCHING =====
def normalise(text):
    """'McDonald’s Été!' → 'mcdonalds ete': lower case, no accents, apostrophes dropped, other signs → spaces."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"['’`]", "", text)          # McDonald's = McDonalds
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def match_keywords(text):
    """Category from the keyword list, or None. Longer keywords are tried first ('metro express' before 'metro')."""
    padded = " " + normalise(text) + " "  # spaces around = whole-word matching
    pairs = [(normalise(word), category) for category, words in CATEGORY_KEYWORDS.items() for word in words]
    for word, category in sorted(pairs, key=lambda pair: -len(pair[0])):
        if word and " " + word + " " in padded:
            return category
    return None


def get_note_words(text):
    """The useful words of a note: no numbers ('350'), no tiny or filler words."""
    return {w for w in normalise(text).split() if len(w) >= MIN_WORD_LENGTH and not w.isdigit() and w not in SKIP_WORDS}


def match_history(text, expenses):
    """The category this user used most often for past notes sharing a word with the text (ties → most recent)."""
    words = get_note_words(text)
    if not words:
        return None
    counts = Counter()
    latest = {}
    for expense in expenses:
        if expense["category"] in CATEGORIES and words & get_note_words(expense["note"]):
            counts[expense["category"]] += 1
            latest[expense["category"]] = max(latest.get(expense["category"], ""), expense["date"])
    if not counts:
        return None
    return max(counts, key=lambda category: (counts[category], latest[category]))


def suggest_category(text, expenses):
    """{category, source}: source = 'history', 'keywords' or None (no guess). expenses = THIS user's rows only."""
    category = match_history(text, expenses)
    if category:
        return {"category": category, "source": "history"}
    category = match_keywords(text)
    return {"category": category, "source": "keywords" if category else None}
