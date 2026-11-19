# budget_plans.py — the budget plans the app offers (edit here, not in the code). Each plan's needs + wants + savings
# = 100 (% of income). "kind" says honestly where a plan comes from: "practitioner" = a rule of thumb from a
# personal-finance book or column; "research" = built on a published study. Names / texts are translated in the
# frontend (plan.<id>.name / .desc / .why); the English here is the fallback and what the API documents.

PLANS = {
    "fifty_thirty_twenty": {
        "name": "50/30/20", "needs": 50, "wants": 30, "savings": 20, "buffer_months": 3, "kind": "practitioner",
        "desc": "Half for needs, 30% for wants, 20% for savings or extra debt payments.",
        "why": "A simple, widely used starting split.",
        "source": "Warren & Warren Tyagi (2005), All Your Worth (book – practitioner rule).",
    },
    "sixty_solution": {
        # committed bills ≤ 60 + irregular costs 10 → both are needs on the bar (70)
        "name": "60% plan", "needs": 70, "wants": 10, "savings": 20, "buffer_months": 3, "kind": "practitioner",
        "desc": "Committed bills up to 60%, 10% irregular costs, 10% fun, 20% savings or debt.",
        "why": "Fits when fixed bills like rent take a big share of income.",
        "source": "R. Jenkins, MSN Money (practitioner rule).",
    },
    "student_caps": {
        "name": "Student caps", "needs": 60, "wants": 30, "savings": 10, "buffer_months": 1, "kind": "research",
        "desc": "60% needs, 30% wants with a cap per category, 10% savings; a 1-month safety buffer.",
        "why": "Separate 'mental budgets' per category make overspending easier to notice and stop.",
        "source": "Heath & Soll (1996) mental budgeting; a small emergency buffer (~1 month of income) "
                  "reduces financial hardship.",
        "category_caps": True,
    },
    "pay_yourself_first": {
        "name": "Pay yourself first", "needs": 50, "wants": 30, "savings": 20, "buffer_months": 3,
        "kind": "research",
        "desc": "Move 20% to savings on payday, before spending. Add 1–2% more each time income rises.",
        "why": "Saving automatically, and raising it with each pay rise, makes saving stick.",
        "source": "Thaler & Benartzi (2004) Save More Tomorrow.",
    },
    "zero_based": {
        "name": "Zero-based", "needs": 55, "wants": 25, "savings": 20, "buffer_months": 3, "kind": "practitioner",
        "desc": "Give every rupee of income a job until 0 is left. Good for irregular income.",
        "why": "When income changes from month to month, planning each rupee avoids surprises.",
        "source": "Zero-based budgeting (practitioner method – no single study behind it).",
    },
    "debt_focus": {
        "name": "Debt first", "needs": 50, "wants": 30, "savings": 20, "buffer_months": 1, "kind": "practitioner",
        "desc": "Like 50/30/20, but the 20% goes to loan repayments first; loan payments count in that 20%.",
        "why": "Paying debt down first cuts the interest you pay.",
        "source": "50/30/20 rule (Warren & Warren Tyagi, 2005) applied to debt (practitioner rule).",
        "loans_in_savings": True,
    },
}

DEFAULT_PLAN = "fifty_thirty_twenty"

# Full citations for the "The research" screen. "kind" = what the source is.
REFERENCES = [
    {"id": "heath_soll_1996", "kind": "research",
     "text": "Heath, C. & Soll, J. B. (1996). Mental budgeting and consumer decisions. "
             "Journal of Consumer Research, 23(1), 40–52."},
    {"id": "thaler_1999", "kind": "research",
     "text": "Thaler, R. H. (1999). Mental accounting matters. Journal of Behavioral Decision Making, 12(3), 183–206."},
    {"id": "thaler_benartzi_2004", "kind": "research",
     "text": "Thaler, R. H. & Benartzi, S. (2004). Save More Tomorrow: Using behavioral economics to increase "
             "employee saving. Journal of Political Economy, 112(S1), S164–S187."},
    {"id": "prelec_loewenstein_1998", "kind": "research",
     "text": "Prelec, D. & Loewenstein, G. (1998). The red and the black: Mental accounting of savings and debt. "
             "Marketing Science, 17(1), 4–28."},
    {"id": "lynch_2010", "kind": "research",
     "text": "Lynch, J. G., Netemeyer, R. G., Spiller, S. A. & Zammit, A. (2010). A generalizable scale of "
             "propensity to plan. Journal of Consumer Research, 37(1), 108–128."},
    {"id": "ashraf_2006", "kind": "research",
     "text": "Ashraf, N., Karlan, D. & Yin, W. (2006). Tying Odysseus to the mast: Evidence from a commitment "
             "savings product in the Philippines. Quarterly Journal of Economics, 121(2), 635–672."},
    {"id": "modigliani_1954", "kind": "research",
     "text": "Modigliani, F. & Brumberg, R. (1954). Utility analysis and the consumption function: An "
             "interpretation of cross-section data (the life-cycle hypothesis)."},
    {"id": "warren_2005", "kind": "practitioner",
     "text": "Warren, E. & Warren Tyagi, A. (2005). All Your Worth: The Ultimate Lifetime Money Plan. Free Press."},
    {"id": "jenkins_msn", "kind": "practitioner",
     "text": "Jenkins, R. The 60% Solution. MSN Money (column)."},
]

# Which ideas in the app come from research (shown on "The research" screen)
RESEARCH_IDEAS = {
    "commitment": "ashraf_2006",       # changes start next month, no dodging the plan = a commitment device
    "mental_budgets": "heath_soll_1996",
    "save_more_tomorrow": "thaler_benartzi_2004",
    "planning": "lynch_2010",
    "life_phase": "modigliani_1954",
}


def is_looser(new_id, current_id):
    """A plan is looser if it lowers the savings % or raises the wants % compared with the current plan."""
    new, current = PLANS[new_id], PLANS[current_id]
    return new["savings"] < current["savings"] or new["wants"] > current["wants"]
