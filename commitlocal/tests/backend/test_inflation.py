# test_inflation.py — the CPI feature: the CSV builder (scripts/build_cpi_csv.py, run on temporary files only),
# the 12-month inflation rate, the goal projection and its edge cases, and the two API endpoints.
# Calculations use tests/fixtures/cpi_sample.csv (FAKE numbers). data/cpi_raw is never touched.
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

from conftest import log_in
from services import inflation

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "cpi_sample.csv"
TODAY = date(2025, 11, 1)


# ===== HELPERS =====
@pytest.fixture
def table():
    return inflation.read_cpi(FIXTURE)


@pytest.fixture
def builder(tmp_path, monkeypatch):
    """The real build script, pointed at a temporary raw folder and output file."""
    spec = importlib.util.spec_from_file_location("build_cpi_csv", ROOT / "scripts" / "build_cpi_csv.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(module, "RAW_DIR", str(raw))
    monkeypatch.setattr(module, "OUT_FILE", str(tmp_path / "out.csv"))
    module.raw_dir, module.out_file = raw, tmp_path / "out.csv"
    return module


def write_release(folder, name, release_date, rows, base="January - December 2023 = 100"):
    lines = [f"# Release date: {release_date}", f"# Base: {base}", "month,division,index_value,base"]
    lines += [f"{m},{division},{value},x" for m, division, value in rows]
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_output(module):
    return module.out_file.read_text(encoding="utf-8").splitlines()


# ===== CSV BUILDER =====
def test_builder_combines_files_and_standardises_names(builder, capsys):
    write_release(builder.raw_dir, "a.csv", "2025-11-07", [("2025-09", "All Divisions", 100), ("2025-10", "1. Transport", 101)])
    write_release(builder.raw_dir, "b.csv", "2025-12-05", [("2025-10", "all items", 100.5), ("2025-11", "Transport", 102)])
    builder.main()
    out = read_output(builder)
    assert out[0] == "month,category,index_value,base_year,source_file"
    assert "2025-09,All Items,100.0,2023,a.csv" in out
    assert "2025-11,Transport,102.0,2023,b.csv" in out
    assert "Months: 2025-09 to 2025-11 (3 months)" in capsys.readouterr().out


def test_builder_rejects_mixed_base_years(builder):
    write_release(builder.raw_dir, "a.csv", "2025-11-07", [("2025-09", "All Items", 100)])
    write_release(builder.raw_dir, "b.csv", "2025-12-05", [("2025-10", "All Items", 100)], base="2017 = 100")
    with pytest.raises(SystemExit, match="different base years"):
        builder.main()


def test_builder_detects_gaps(builder, capsys):
    write_release(builder.raw_dir, "a.csv", "2025-11-07", [("2025-01", "All Items", 100), ("2025-04", "All Items", 101)])
    builder.main()
    printed = capsys.readouterr().out
    assert "Gap: 2 missing month(s) after 2025-01" in printed
    assert "need 13" in printed


def test_builder_keeps_newest_release_for_duplicate_months(builder, capsys):
    write_release(builder.raw_dir, "old.csv", "2025-11-07", [("2025-10", "All Items", 100)])
    write_release(builder.raw_dir, "new.csv", "2025-12-05", [("2025-10", "All Items", 100.2)])
    builder.main()
    assert "2025-10,All Items,100.2,2023,new.csv" in read_output(builder)
    assert "new.csv says 100.2, old.csv says 100.0" in capsys.readouterr().out  # values disagree → warning


# ===== 12-MONTH RATE =====
def test_annual_rate_on_fixture(table):
    assert inflation.get_annual_rate(table, "All Items") == pytest.approx(0.10)
    assert inflation.get_annual_rate(table, "Information and communication") == pytest.approx(-0.05)
    assert inflation.get_annual_rate(table, "Transport") is None  # only 3 months
    assert inflation.get_annual_rate(table, "All Items", years=3) is None  # needs 37 months


def test_real_data_all_items_rate_matches_official_figure():
    real = inflation.read_cpi(inflation.DATA_FILE)
    assert real.index[-1] == "2026-10"
    assert round(inflation.get_annual_rate(real, "All Items") * 100, 1) == 6.4


def test_missing_file_means_unavailable(monkeypatch, tmp_path):
    assert inflation.read_cpi(tmp_path / "nope.csv") is None
    monkeypatch.setitem(inflation._cpi, "loaded", True)
    monkeypatch.setitem(inflation._cpi, "table", None)
    result = inflation.project_goal(1000, 0, date(2030, 1, 1))
    assert result["available"] is False and result["reason"] == "DATA_UNAVAILABLE"


# ===== PROJECTION =====
def test_projection_hand_calculated(table):
    # 24 months at 10%/year: 30,000 × 1.1² = 36,300
    p = inflation.project_goal(30000, 0, date(2027, 11, 1), "Other", today=TODAY, table=table)
    assert p["available"] and p["months"] == 24
    assert p["projected_cost"] == 36300
    assert p["extra_needed"] == 6300
    assert p["monthly_saving_original"] == 1250
    assert p["monthly_saving_adjusted"] == 1512.5
    assert p["inflation_rate_used"] == 10.0
    assert p["category_used"] == "All Items" and p["data_as_of"] == "2025-10"
    assert p["source"] == "Statistics Mauritius – Consumer Price Index"
    assert p["warnings"] == []


def test_falls_back_to_all_items(table):
    p = inflation.project_goal(1000, 0, date(2026, 11, 1), "Car", today=TODAY, table=table)
    assert p["category_used"] == "All Items" and p["fell_back_to_all_items"]
    assert p["warnings"][0]["code"] == "FALLBACK_ALL_ITEMS"


def test_no_category_uses_all_items_without_warning(table):
    p = inflation.project_goal(1000, 0, date(2026, 11, 1), None, today=TODAY, table=table)
    assert p["category_used"] == "All Items" and not p["fell_back_to_all_items"]


def test_past_deadline_and_less_than_a_month(table):
    assert inflation.project_goal(1000, 0, date(2025, 10, 31), today=TODAY, table=table)["reason"] == "DEADLINE_PASSED"
    soon = inflation.project_goal(1000, 0, date(2025, 11, 30), today=TODAY, table=table)
    assert soon["available"] is False and soon["reason"] == "DEADLINE_TOO_SOON"


def test_over_five_years_warns(table):
    p = inflation.project_goal(1000, 0, date(2031, 11, 1), today=TODAY, table=table)
    assert p["available"] and p["months"] == 72
    assert "LONG_HORIZON" in [w["code"] for w in p["warnings"]]


def test_negative_inflation_lowers_cost(table):
    p = inflation.project_goal(30000, 0, date(2026, 11, 1), "Phone", today=TODAY, table=table)
    assert p["category_used"] == "Information and communication"
    assert p["inflation_rate_used"] == -5.0
    assert p["projected_cost"] == 28500 and p["extra_needed"] == -1500
    assert p["monthly_saving_adjusted"] < p["monthly_saving_original"]


def test_fully_funded_goal_is_flagged(table):
    p = inflation.project_goal(1000, 1000, date(2026, 11, 1), today=TODAY, table=table)
    assert p["fully_funded"] and p["funded_but_short"]
    assert p["monthly_saving_original"] == 0 and p["monthly_saving_adjusted"] == pytest.approx(100 / 12, abs=0.01)
    assert "FUNDED_BUT_SHORT" in [w["code"] for w in p["warnings"]]


# ===== API =====
EXPECTED_FIELDS = {"projected_cost", "extra_needed", "monthly_saving_original", "monthly_saving_adjusted",
                   "inflation_rate_used", "category_used", "data_as_of", "source"}


@pytest.fixture
def api(logged_in, table, monkeypatch):
    monkeypatch.setitem(inflation._cpi, "loaded", True)
    monkeypatch.setitem(inflation._cpi, "table", table)
    return logged_in


def test_goal_projection_endpoint(api):
    deadline = (date.today() + timedelta(days=400)).isoformat()
    res = api.post("/api/goals", json={"name": "Phone", "target_amount": 30000, "deadline": deadline, "category": "Phone"})
    goal = res.json()["goals"][0]
    assert goal["category"] == "Phone"
    p = api.get(f"/api/goals/{goal['id']}/inflation-projection").json()
    assert EXPECTED_FIELDS <= p.keys()
    assert p["category_used"] == "Information and communication" and p["projected_cost"] < 30000


def test_goal_projection_is_private(api, new_client, sent_codes):
    deadline = (date.today() + timedelta(days=400)).isoformat()
    goal = api.post("/api/goals", json={"name": "Bike", "target_amount": 5000, "deadline": deadline}).json()["goals"][0]
    other = log_in(new_client(), sent_codes, "ravi@example.com")
    assert other.get(f"/api/goals/{goal['id']}/inflation-projection").status_code == 404


def test_preview_endpoint(api):
    deadline = (date.today() + timedelta(days=400)).isoformat()
    res = api.get("/api/inflation/projection", params={"target": 30000, "current": 0, "deadline": deadline,
                                                       "category": "Electronics"})
    assert res.status_code == 200 and EXPECTED_FIELDS <= res.json().keys()


def test_preview_checks_input(api):
    deadline = (date.today() + timedelta(days=400)).isoformat()
    bad = api.get("/api/inflation/projection", params={"target": 100, "deadline": deadline, "category": "Spaceship"})
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_CATEGORY"
    negative = api.get("/api/inflation/projection", params={"target": -5, "deadline": deadline})
    assert negative.status_code == 422 and negative.json()["code"] == "INVALID_AMOUNT"
    form = api.post("/api/goals", json={"name": "X", "target_amount": 10, "deadline": deadline, "category": "Spaceship"})
    assert form.status_code == 422 and form.json()["code"] == "INVALID_CATEGORY"


def test_preview_needs_login(client):
    assert client.get("/api/inflation/projection", params={"target": 1, "deadline": "2030-01-01"}).status_code == 401
