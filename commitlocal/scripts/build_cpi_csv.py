"""Build data/cpi_mauritius.csv from the raw Statistics Mauritius CPI releases.

Each file in data/cpi_raw/ is one monthly release, transcribed from the
"Sub-indices by division" table of the official PDF. Header lines starting
with '#' record the source URL, release date and base period.

Run from the project root:
    python scripts/build_cpi_csv.py
"""
import csv
import glob
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "cpi_raw")
OUT_FILE = os.path.join(ROOT, "data", "cpi_mauritius.csv")

# Same division, one spelling. Keys are lower-case for matching.
NAME_FIXES = {
    "all divisions": "All Items",
    "all items": "All Items",
    "food and non-alcoholic beverages": "Food and non-alcoholic beverages",
    "alcoholic beverages and tobacco": "Alcoholic beverages and tobacco",
    "clothing and footwear": "Clothing and footwear",
    "housing, water, electricity, gas and other fuels": "Housing, water, electricity, gas and other fuels",
    "furnishings, household equipment and routine household maintenance":
        "Furnishings, household equipment and routine household maintenance",
    "health": "Health",
    "transport": "Transport",
    "information and communication": "Information and communication",
    "recreation, sports and culture": "Recreation, sports and culture",
    "education services": "Education services",
    "restaurants and accommodation services": "Restaurants and accommodation services",
    "insurance and financial services": "Insurance and financial services",
    "personal care, social protection and miscellaneous goods and services":
        "Personal care, social protection and miscellaneous goods and services",
}


def standardise(name):
    clean = re.sub(r"^\d+\.\s*", "", name.strip())  # drop "1. " numbering
    clean = re.sub(r"\s+", " ", clean)
    key = clean.lower()
    if key not in NAME_FIXES:
        raise ValueError(f"Unknown category name: {name!r}")
    return NAME_FIXES[key]


def read_release(path):
    meta, rows = {}, []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("#"):
            m = re.match(r"#\s*([^:]+):\s*(.*)", line.strip())
            if m:
                meta[m.group(1).strip().lower()] = m.group(2).strip()
    data = [l for l in lines if not l.startswith("#")]
    for r in csv.DictReader(data):
        rows.append(r)
    if "release date" not in meta or "base" not in meta:
        raise ValueError(f"{os.path.basename(path)} is missing its release date or base header")
    return meta, rows


def month_index(ym):
    y, m = map(int, ym.split("-"))
    return y * 12 + (m - 1)


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
    if not files:
        sys.exit(f"No raw files found in {RAW_DIR}")

    warnings = []
    bases = defaultdict(list)
    # (month, category) -> (release_date, value, source_file)
    best = {}

    for path in files:
        name = os.path.basename(path)
        meta, rows = read_release(path)
        base_year = re.search(r"(\d{4})\s*=\s*100", meta["base"]).group(1)
        bases[base_year].append(name)
        for r in rows:
            month = r["month"].strip()
            if not re.fullmatch(r"\d{4}-\d{2}", month):
                raise ValueError(f"{name}: bad month {month!r}")
            cat = standardise(r["division"])
            value = float(r["index_value"])
            key = (month, cat)
            entry = (meta["release date"], value, name, base_year)
            if key in best:
                old = best[key]
                if old[1] != value:
                    warnings.append(f"{month} {cat}: {old[2]} says {old[1]}, {name} says {value}")
                if entry[0] > old[0]:
                    best[key] = entry
            else:
                best[key] = entry

    if len(bases) > 1:
        detail = "; ".join(f"base {b}=100: {', '.join(fs)}" for b, fs in bases.items())
        sys.exit(f"ERROR: files use different base years, not mixing them. {detail}")
    base_year = next(iter(bases))

    months = sorted({m for m, _ in best})
    categories = sorted({c for _, c in best}, key=lambda c: (c != "All Items", c))

    # gaps and completeness
    idx = [month_index(m) for m in months]
    for a, b in zip(idx, idx[1:]):
        if b - a > 1:
            warnings.append(f"Gap: {b - a - 1} missing month(s) after {months[idx.index(a)]}")
    for m in months:
        missing = [c for c in categories if (m, c) not in best]
        if missing:
            warnings.append(f"{m} is missing: {', '.join(missing)}")
    run = longest = 1
    for a, b in zip(idx, idx[1:]):
        run = run + 1 if b - a == 1 else 1
        longest = max(longest, run)
    if longest < 13:
        warnings.append(f"Only {longest} consecutive months - need 13 for a 12-month inflation rate")

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "category", "index_value", "base_year", "source_file"])
        for m in months:
            for c in categories:
                if (m, c) in best:
                    _, v, src, _ = best[(m, c)]
                    w.writerow([m, c, v, base_year, src])

    print(f"Wrote {OUT_FILE}")
    print(f"Base: {base_year} = 100 (all {len(files)} files agree)")
    print(f"Months: {months[0]} to {months[-1]} ({len(months)} months)")
    print(f"Categories ({len(categories)}): {', '.join(categories)}")
    if warnings:
        print("Warnings:")
        for w_ in warnings:
            print("  -", w_)
    else:
        print("Warnings: none (overlapping months agree across releases, no gaps)")


if __name__ == "__main__":
    main()
