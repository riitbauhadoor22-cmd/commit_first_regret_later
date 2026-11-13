# game/events.py — surprise events: picks one at the start of a game and works out what it changes (in cents).
import random

from money import to_cents


# ===== PICK =====
def choose_event(level, events_on, rng=random):
    """One random event of this level, or None when the player turned events off."""
    if not events_on or not level["events"]:
        return None
    return rng.choice(level["events"])


# ===== EFFECT =====
def event_changes(event):
    """(extra income in cents, {category: change of its minimum in cents}). Discounts lower a minimum."""
    if event is None:
        return 0, {}
    amount = to_cents(event["amount"])
    if event["type"] == "bonus":
        return amount, {}
    return 0, {event["category"]: amount if event["type"] == "cost" else -amount}
