# rate_limit.py — simple in-memory rate limits for the login / code routes (per IP and per account).
# Fine for ONE server instance (Render free plan). Counts are lost on restart; the database limits in
# routes/auth.py (wrong codes per hour, codes per day per account) are kept.
import threading
import time
from collections import deque

from errors import AppError

# ===== STATE =====
enabled = True       # tests switch this off (conftest.py) and back on for the limiter tests
MAX_KEYS = 10_000    # forget old keys when there are more than this (keeps memory small)
_hits = {}           # key (e.g. "login-ip:1.2.3.4") -> deque of times (seconds)
_lock = threading.Lock()  # routes run in several threads


# ===== HELPERS =====
def reset():
    with _lock:
        _hits.clear()


def client_ip(request):
    """The caller's IP. On Render uvicorn --proxy-headers puts the real one in request.client."""
    return request.client.host if request.client else "unknown"


def _recent(key, window, now):
    """The key's times inside the window (older ones are dropped)."""
    times = _hits.setdefault(key, deque())
    while times and times[0] <= now - window:
        times.popleft()
    return times


def _forget_old_keys(now):
    if len(_hits) > MAX_KEYS:
        for key in [k for k, times in _hits.items() if not times or times[-1] <= now - 86400]:
            del _hits[key]


def too_many(retry_after):
    error = AppError(429, "TOO_MANY_REQUESTS", "Too many tries. Please wait a little and try again.")
    error.headers = {"Retry-After": str(max(int(retry_after), 1))}  # seconds until the oldest try expires
    return error


# ===== LIMITS =====
def check(key, limit, window):
    """429 if `key` already has `limit` hits in the last `window` seconds (does not count a new hit)."""
    if not enabled:
        return
    with _lock:
        now = time.monotonic()
        times = _recent(key, window, now)
        if len(times) >= limit:
            raise too_many(times[0] + window - now)


def add(key):
    """Counts one hit for `key` (e.g. a wrong code, a code sent)."""
    if not enabled:
        return
    with _lock:
        now = time.monotonic()
        _forget_old_keys(now)
        _hits.setdefault(key, deque()).append(now)


def hit(key, limit, window):
    """check() + add(): counts this request and refuses it when over the limit."""
    check(key, limit, window)
    add(key)
