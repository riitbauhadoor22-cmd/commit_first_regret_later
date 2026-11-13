# test_income_summary.py — Money in (regular + one-off income), fixed bills, budgets (none / under / at / over)
# and the Money tab summary maths (In, Out, Saved, Left to spend, Needs / Wants / Savings %), month by month.
import pytest

from money import get_this_month


def add_income(client, amount, frequency, date, name="Job", type_="Salary"):
    res = client.post("/api/income", json={"name": name, "type": type_, "amount": amount,
                                           "frequency": frequency, "date": date})
    assert res.status_code == 201
    return res.json()


def add_expense(client, amount, category, date, is_fixed=False, **extra):
    res = client.post("/api/expenses", json={"amount": amount, "category": category, "date": date,
                                             "is_fixed": is_fixed, **extra})
    assert res.status_code == 201
    return res.json()


def summary(client, month):
    res = client.get("/api/summary", params={"month": month})
    assert res.status_code == 200
    return res.json()


def row(summary_body, category):
    return next(r for r in summary_body["categories"] if r["category"] == category)


# ===== MONEY IN =====
def test_regular_income_counts_from_its_start_month(logged_in):  # monthly income: not before, yes in and after start
    add_income(logged_in, 20000, "monthly", "2026-03-15")
    assert summary(logged_in, "2026-02")["income"] == 0
    assert summary(logged_in, "2026-03")["income"] == 20000
    assert summary(logged_in, "2027-01")["income"] == 20000


def test_one_off_income_only_in_its_own_month(logged_in):  # one-off: only the month it was received
    add_income(logged_in, 5000, "one-off", "2026-03-02", name="Gift", type_="Other")
    assert [summary(logged_in, m)["income"] for m in ("2026-02", "2026-03", "2026-04")] == [0, 5000, 0]
    listed = logged_in.get("/api/income", params={"month": "2026-03"}).json()
    assert len(listed["one_off"]) == 1 and listed["regular"] == []


def test_weekly_income_is_52_over_12(logged_in):  # weekly 1200 -> 1200 x 52 / 12 = 5200 a month
    add_income(logged_in, 1200, "weekly", "2026-01-01")
    assert summary(logged_in, "2026-05")["income"] == 5200


def test_edit_and_delete_income(logged_in):  # edit changes the amount/type; delete removes it
    income = add_income(logged_in, 1000, "monthly", "2026-01-01")
    res = logged_in.put(f"/api/income/{income['id']}", json={"name": "Shop", "type": "Side hustle",
                                                             "amount": 1500, "frequency": "one-off", "date": "2026-02-10"})
    assert res.status_code == 200 and res.json()["amount"] == 1500 and res.json()["frequency"] == "one-off"
    assert summary(logged_in, "2026-01")["income"] == 0 and summary(logged_in, "2026-02")["income"] == 1500
    assert logged_in.delete(f"/api/income/{income['id']}").status_code == 200
    assert summary(logged_in, "2026-02")["income"] == 0


@pytest.mark.parametrize("changes", [{"amount": -5}, {"amount": 0}, {"amount": "abc"}, {"amount": 1e20},
                                     {"name": ""}, {"name": "   "}, {"type": "Lottery"}, {"frequency": "daily"},
                                     {"date": "not-a-date"}])
def test_bad_income_is_rejected(logged_in, changes):  # bad income -> 400/422, never saved
    body = {"name": "Job", "type": "Salary", "amount": 100, "frequency": "monthly", "date": "2026-01-01", **changes}
    assert logged_in.post("/api/income", json=body).status_code in (400, 422)
    assert logged_in.get("/api/income", params={"month": "2026-01"}).json()["regular"] == []


# ===== MONEY OUT =====
def test_fixed_bill_repeats_every_month_from_its_start(logged_in):  # "repeats every month" -> counted from start month on
    add_expense(logged_in, 800, "Bills", "2026-03-05", is_fixed=True)
    assert summary(logged_in, "2026-02")["spent"] == 0
    assert summary(logged_in, "2026-03")["spent"] == 800 and summary(logged_in, "2026-09")["fixed_total"] == 800


def test_everyday_expense_stays_in_its_month(logged_in):  # switching month keeps data in the right month
    add_expense(logged_in, 120, "Transport", "2026-04-30")
    add_expense(logged_in, 80, "Transport", "2026-05-01")
    assert summary(logged_in, "2026-04")["spent"] == 120 and summary(logged_in, "2026-05")["spent"] == 80
    may = logged_in.get("/api/expenses", params={"month": "2026-05"}).json()
    assert [e["amount"] for e in may["everyday"]] == [80]


@pytest.mark.parametrize("spent, over_by, percent", [(0, 0, 0.0), (300, 0, 60.0), (500, 0, 100.0), (650, 150, 130.0)])
def test_spent_vs_budget(logged_in, spent, over_by, percent):  # none / under / exactly at / over the budget
    logged_in.put("/api/budgets", json={"category": "Shopping", "monthly_limit": 500})
    if spent:
        add_expense(logged_in, spent, "Shopping", "2026-06-10")
    r = row(summary(logged_in, "2026-06"), "Shopping")
    assert (r["spent"], r["budget"], r["over_by"], r["percent"]) == (spent, 500, over_by, percent)


def test_category_without_budget(logged_in):  # no budget -> budget None, 0%, never over
    add_expense(logged_in, 999, "Fun & outings", "2026-06-10")
    r = row(summary(logged_in, "2026-06"), "Fun & outings")
    assert r["budget"] is None and r["percent"] == 0 and r["over_by"] == 0


def test_real_budget_routes_return_200(logged_in):  # GET /api/budgets and the /api/budget alias both work
    assert logged_in.get("/api/budgets").status_code == 200
    assert logged_in.get("/api/budget").status_code == 200


# ===== SUMMARY CARD MATHS =====
def test_summary_card_maths(logged_in):  # In, Out, Saved, Left to spend and the 50/30/20 percentages
    month = get_this_month()  # deposits are always dated today
    add_income(logged_in, 10000, "monthly", month + "-01")
    add_expense(logged_in, 3000, "Bills", month + "-01", is_fixed=True)    # need
    add_expense(logged_in, 1000, "Groceries", month + "-02")               # need
    add_expense(logged_in, 1500, "Shopping", month + "-03")                # want
    add_expense(logged_in, 500, "Shopping", month + "-03", kind="need")    # want category saved as a need
    assert logged_in.post("/api/savings/safety-net/add-money", json={"amount": 1000}).status_code == 200
    s = summary(logged_in, month)
    assert (s["income"], s["spent"], s["saved"], s["left_to_spend"]) == (10000, 6000, 1000, 3000)
    assert (s["needs_percent"], s["wants_percent"], s["savings_percent"]) == (45.0, 15.0, 10.0)


def test_summary_with_no_income_has_no_division_by_zero(logged_in):  # 0 income -> 0%, negative left to spend
    add_expense(logged_in, 250, "Groceries", "2026-07-01")
    s = summary(logged_in, "2026-07")
    assert s["needs_percent"] == 0 and s["left_to_spend"] == -250


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "abc", "2026-00"])
def test_bad_month_is_rejected(logged_in, month):  # bad month text -> 422, not 500
    assert logged_in.get("/api/summary", params={"month": month}).status_code == 422
