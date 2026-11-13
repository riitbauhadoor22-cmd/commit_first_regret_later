# tests/test_money.py — checks every calculation in money.py with small, hand-made examples.
from money import (get_amount_to_add, get_bank_bar, get_category_spending, get_goal_statuses,
                   format_rupees, get_goals_warning, get_monthly_income, get_monthly_target, get_months_left,
                   get_needs_per_month, get_quick_add, get_regular_income, get_safety_net,
                   get_saved_in_month, get_summary, get_total_spent)


# ===== EXAMPLE ROWS =====
def income(amount, frequency, day, id=1):
    return {"id": id, "name": "x", "type": "Salary", "amount": amount, "frequency": frequency, "date": day}


def expense(amount, day, category="Food & drinks", kind="want", note="", is_fixed=0, id=1):
    return {"id": id, "amount": amount, "category": category, "kind": kind, "note": note,
            "date": day, "is_fixed": is_fixed, "source": "typed"}


def goal(id, target, saved, deadline, priority):
    return {"id": id, "name": f"Goal {id}", "target_amount": target, "saved_amount": saved,
            "deadline": deadline, "priority": priority}


# ===== 1. MONTHLY INCOME =====
def test_monthly_income_adds_monthly_weekly_and_this_months_one_offs():
    incomes = [
        income(10000, "monthly", "2026-01-01"),
        income(600, "weekly", "2026-10-05"),       # 600 × 52 ÷ 12 = 2600
        income(500, "one-off", "2026-11-20"),      # this month
        income(9999, "one-off", "2026-10-20"),     # last month: not counted
    ]
    assert get_monthly_income(incomes, "2026-11") == 13100


def test_repeating_income_only_counts_from_its_start_month():
    incomes = [income(10000, "monthly", "2026-11-15")]
    assert get_monthly_income(incomes, "2026-10") == 0
    assert get_monthly_income(incomes, "2026-11") == 10000
    assert get_monthly_income(incomes, "2027-03") == 10000  # never copied, still counted


def test_regular_income_leaves_out_one_offs():
    incomes = [income(10000, "monthly", "2026-01-01"), income(500, "one-off", "2026-11-02")]
    assert get_regular_income(incomes, "2026-11") == 10000


# ===== 3. SPENT =====
def test_spent_is_fixed_bills_plus_this_months_everyday_expenses():
    expenses = [
        expense(1500, "2026-09-01", category="Bills", kind="need", is_fixed=1),  # rent, from September
        expense(200, "2026-11-03"),
        expense(300, "2026-10-30"),                                             # last month
        expense(800, "2026-12-01", is_fixed=1),                                 # starts next month
    ]
    assert get_total_spent(expenses, "2026-11") == 1700


# ===== 4. SAVED =====
def test_saved_is_deposits_dated_this_month():
    deposits = [{"amount": 500, "date": "2026-11-01"}, {"amount": 250, "date": "2026-11-30"},
                {"amount": 999, "date": "2026-10-31"}]
    assert get_saved_in_month(deposits, "2026-11") == 750


# ===== 5. SUMMARY + PERCENTS =====
def test_summary_left_to_spend_and_percents():
    incomes = [income(10000, "monthly", "2026-01-01")]
    expenses = [
        expense(4000, "2026-11-01", category="Bills", kind="need", is_fixed=1),
        expense(1000, "2026-11-05", category="Groceries", kind="need"),
        expense(2000, "2026-11-06", category="Shopping", kind="want"),
    ]
    deposits = [{"amount": 1500, "date": "2026-11-10"}]
    s = get_summary(incomes, expenses, deposits, [], "2026-11")
    assert s["income"] == 10000
    assert s["spent"] == 7000
    assert s["saved"] == 1500
    assert s["left_to_spend"] == 1500
    assert s["needs_percent"] == 50.0
    assert s["wants_percent"] == 20.0
    assert s["savings_percent"] == 15.0
    assert s["fixed_total"] == 4000


def test_percents_are_zero_with_no_income():
    s = get_summary([], [expense(100, "2026-11-01")], [], [], "2026-11")
    assert s["needs_percent"] == 0 and s["wants_percent"] == 0 and s["savings_percent"] == 0
    assert s["left_to_spend"] == -100


def test_recent_is_the_last_3_everyday_expenses():
    expenses = [expense(10 * i, f"2026-11-0{i}", id=i) for i in range(1, 6)]
    recent = get_summary([], expenses, [], [], "2026-11")["recent"]
    assert [e["id"] for e in recent] == [5, 4, 3]


# ===== CATEGORY ROWS + BUDGETS =====
def test_category_over_budget_shows_how_much():
    expenses = [expense(1800, "2026-11-02", category="Food & drinks")]
    budgets = [{"category": "Food & drinks", "monthly_limit": 1500}]
    rows = {r["category"]: r for r in get_category_spending(expenses, budgets, "2026-11")}
    assert rows["Food & drinks"]["over_by"] == 300
    assert rows["Food & drinks"]["percent"] == 120.0
    assert rows["Groceries"]["budget"] is None  # no budget → "Set budget" link


def test_category_rows_leave_out_fixed_bills():
    expenses = [expense(500, "2026-11-01", category="Subscriptions", is_fixed=1)]
    rows = {r["category"]: r for r in get_category_spending(expenses, [], "2026-11")}
    assert rows["Subscriptions"]["spent"] == 0


# ===== SAVING TARGET + SAFETY NET =====
def test_monthly_target_defaults_to_20_percent_of_regular_income():
    incomes = [income(18500, "monthly", "2026-01-01"), income(5000, "one-off", "2026-11-01")]
    assert get_monthly_target(None, incomes, "2026-11") == 3700
    assert get_monthly_target(2500, incomes, "2026-11") == 2500


def test_safety_net_is_3_times_fixed_bills():
    expenses = [expense(2000, "2026-01-01", is_fixed=1, id=1), expense(1000, "2026-05-01", is_fixed=1, id=2)]
    net = get_safety_net(expenses, 4500, "2026-11")
    assert net["target"] == 9000
    assert net["percent"] == 50.0


def test_safety_net_percent_stops_at_100():
    expenses = [expense(1000, "2026-01-01", is_fixed=1)]
    assert get_safety_net(expenses, 5000, "2026-11")["percent"] == 100.0


# ===== 6. GOAL NEEDS PER MONTH =====
def test_months_left_is_at_least_1():
    assert get_months_left("2026-11-13", "2027-03-01") == 4
    assert get_months_left("2026-11-13", "2026-11-30") == 1
    assert get_months_left("2026-11-13", "2026-01-01") == 1  # deadline already passed


def test_needs_per_month():
    assert get_needs_per_month(goal(1, 15000, 3000, "2027-05-01", 1), "2026-11-13") == 2000


# ===== 7. GOAL STATUS =====
def test_goals_get_money_in_priority_order():
    goals = [
        goal(1, 6000, 0, "2027-05-01", 2),   # Medium, needs 1000/month
        goal(2, 12000, 0, "2027-05-01", 1),  # High, needs 2000/month
        goal(3, 3000, 0, "2027-05-01", 3),   # Low, needs 500/month
    ]
    results = get_goal_statuses(goals, 3200, "2026-11-13")
    status = {g["id"]: g["status"] for g in results}
    assert [g["id"] for g in results] == [2, 1, 3]
    assert status == {2: "On track", 1: "On track", 3: "Needs more"}  # only 200 left for goal 3


def test_finished_goal_is_done():
    results = get_goal_statuses([goal(1, 1000, 1000, "2027-01-01", 1)], 0, "2026-11-13")
    assert results[0]["status"] == "Done"
    assert results[0]["percent"] == 100.0


def test_warning_when_goals_need_more_than_target():
    assert get_goals_warning(5000, 3700) == ("Your goals need Rs 5,000 a month, but you save Rs 3,700. "
                                             "Push a date back or focus on one goal first.")
    assert get_goals_warning(3000, 3700) is None


# ===== 8. ADDING MONEY =====
def test_add_money_never_goes_above_target():
    assert get_amount_to_add(500, 1000, 200) == 500
    assert get_amount_to_add(5000, 1000, 200) == 800
    assert get_amount_to_add(100, 1000, 1000) == 0


def test_bank_bar_splits_the_balance():
    goals = [{"id": 1, "name": "Phone", "saved_amount": 3000}]
    bar = get_bank_bar(10000, 2000, goals)
    assert [(p["label"], p["amount"], p["percent"]) for p in bar] == [
        ("Safety net", 2000, 20.0), ("Phone", 3000, 30.0), ("Free", 5000, 50.0)]


# ===== 9. QUICK ADD =====
def test_quick_add_picks_the_4_most_repeated_from_last_30_days():
    today = "2026-11-13"
    expenses = []
    next_id = 1
    for note, amount, times in [("Bus", 38, 5), ("Coffee", 120, 4), ("Lunch", 245, 3), ("Snack", 50, 2), ("Movie", 300, 1)]:
        for _ in range(times):
            expenses.append(expense(amount, "2026-11-10", note=note, id=next_id))
            next_id += 1
    expenses.append(expense(999, "2026-09-01", note="Old", id=100))  # older than 30 days
    expenses.append(expense(999, "2026-09-01", note="Old", id=101))
    chips = get_quick_add(expenses, today)
    assert [c["label"] for c in chips] == ["Bus Rs 38", "Coffee Rs 120", "Lunch Rs 245", "Snack Rs 50"]


def test_quick_add_groups_same_note_ignoring_capitals():
    expenses = [expense(38, "2026-11-10", note="Bus", id=1), expense(38, "2026-11-11", note="bus", id=2),
                expense(40, "2026-11-11", note="bus", id=3)]
    chips = get_quick_add(expenses, "2026-11-13")
    assert chips[0]["amount"] == 38 and chips[0]["times"] == 2


def test_format_rupees_uses_indian_grouping():
    assert format_rupees(38) == "38"
    assert format_rupees(3700) == "3,700"
    assert format_rupees(150000) == "1,50,000"
    assert format_rupees(245.5) == "245.50"
