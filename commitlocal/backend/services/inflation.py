# services/inflation.py — the inflation "real cost" estimate for savings goals.
# Loads the official Statistics Mauritius CPI (data/cpi_mauritius.csv, built by scripts/build_cpi_csv.py) once,
# works out a category's yearly inflation rate and projects what a goal will cost by its deadline.
# Results are ESTIMATES only. No CPI numbers are made up here: if the file is missing we say "unavailable".
import datetime
from pathlib import Path

import pandas as pd

from categories import GOAL_CPI_CATEGORIES

# ===== SETTINGS =====
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/services/ → project root (not the CWD)
DATA_FILE = PROJECT_ROOT / "data" / "cpi_mauritius.csv"
SOURCE = "Statistics Mauritius – Consumer Price Index"
ALL_ITEMS = "All Items"
LONG_HORIZON_MONTHS = 60  # over 5 years → add a "less reliable" warning

# ===== CACHED DATA =====
_cpi = {"table": None, "loaded": False}


def read_cpi(path):
    """CSV → table with one row per month ('YYYY-MM') and one column per CPI category. None if missing/broken."""
    try:
        raw = pd.read_csv(path, dtype={"month": str}, comment="#")  # "#" lines = notes (e.g. the test file label)
        return raw.pivot_table(index="month", columns="category", values="index_value", aggfunc="last").sort_index()
    except (OSError, ValueError, KeyError):
        return None


def load_cpi(path=DATA_FILE):
    """Read the CPI file once (called at startup) and keep it in memory."""
    _cpi["table"], _cpi["loaded"] = read_cpi(path), True
    return _cpi["table"]


def get_cpi():
    """The cached CPI table (loads it the first time), or None when the data is unavailable."""
    if not _cpi["loaded"]:
        load_cpi()
    return _cpi["table"]


# ===== DATE HELPERS =====
def shift_month(month, delta):
    """'2026-10', -12 → '2025-10'"""
    year, mon = map(int, month.split("-"))
    total = year * 12 + (mon - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def count_full_months(today, deadline):
    """Whole months from today to the deadline (14 Nov → 13 Dec is 0, → 14 Dec is 1). Negative if passed."""
    months = (deadline.year - today.year) * 12 + (deadline.month - today.month)
    return months - 1 if deadline.day < today.day else months


# ===== INFLATION RATE =====
def get_annual_rate(table, category, years=1):
    """Yearly inflation for a category: index[latest] / index[latest − 12 months] − 1
    (or the 3-year average (index[latest] / index[latest − 36])^(1/3) − 1). None if the months aren't there."""
    if table is None or category not in table.columns:
        return None
    values = table[category].dropna()
    if values.empty:
        return None
    latest = values.index[-1]
    earlier = shift_month(latest, -12 * years)
    if earlier not in values.index:
        return None  # e.g. fewer than 13 months
    return (values[latest] / values[earlier]) ** (1 / years) - 1


def pick_rate(table, goal_category, years=1):
    """(CPI category used, rate, notes) — falls back to All Items when the category can't be used."""
    notes = []
    if years == 3 and get_annual_rate(table, ALL_ITEMS, 3) is None:
        years = 1
        notes.append(("THREE_YEAR_UNAVAILABLE", "Not enough data for a 3-year average, so the 12-month rate is used."))
    cpi_category = GOAL_CPI_CATEGORIES.get(goal_category or "", ALL_ITEMS)
    rate = get_annual_rate(table, cpi_category, years)
    if rate is None and cpi_category != ALL_ITEMS:
        notes.append(("FALLBACK_ALL_ITEMS",
                      f"No usable data for {cpi_category}, so overall inflation (All Items) is used."))
        cpi_category = ALL_ITEMS
        rate = get_annual_rate(table, ALL_ITEMS, years)
    return cpi_category, rate, years, notes


# ===== PROJECTION =====
def unavailable(reason, message):
    return {"available": False, "reason": reason, "message": message, "source": SOURCE}


def project_goal(target, current, deadline, category=None, today=None, table=None, years=1):
    """What the goal may cost at its deadline after inflation, and the monthly saving needed.
    projected_cost = target × (1 + r) ^ (months / 12)."""
    table = get_cpi() if table is None else table
    if table is None:
        return unavailable("DATA_UNAVAILABLE", "Inflation data unavailable.")
    today = today or datetime.date.today()
    months = count_full_months(today, deadline)
    if deadline < today:
        return unavailable("DEADLINE_PASSED", "The deadline has passed, so there is no inflation estimate.")
    if months < 1:
        return unavailable("DEADLINE_TOO_SOON", "The deadline is less than a month away, so inflation won't matter much.")
    cpi_category, rate, years, notes = pick_rate(table, category, years)
    if rate is None:
        return unavailable("DATA_UNAVAILABLE", "Inflation data unavailable.")

    projected = round(target * (1 + rate) ** (months / 12))  # nearest rupee
    if months > LONG_HORIZON_MONTHS:
        notes.append(("LONG_HORIZON", "Estimates more than 5 years ahead are less reliable."))
    funded = current >= target
    if funded and projected > current:
        notes.append(("FUNDED_BUT_SHORT", "You've reached your target, but with inflation it may cost more than you've saved."))
    return {
        "available": True,
        "projected_cost": projected,
        "extra_needed": round(projected - target, 2),  # negative when prices fall
        "monthly_saving_original": round(max(target - current, 0) / months, 2),
        "monthly_saving_adjusted": round(max(projected - current, 0) / months, 2),
        "months": months,
        "inflation_rate_used": round(rate * 100, 2),  # percent per year
        "rate_period": "3y" if years == 3 else "12m",
        "category_used": cpi_category,
        "goal_category": category,
        "fell_back_to_all_items": any(code == "FALLBACK_ALL_ITEMS" for code, _ in notes),
        "fully_funded": funded,
        "funded_but_short": funded and projected > current,
        "data_as_of": table.index[-1],
        "source": SOURCE,
        "warnings": [{"code": code, "message": text} for code, text in notes],
        "estimate_only": True,
    }
