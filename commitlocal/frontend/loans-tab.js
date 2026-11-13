// loans-tab.js — draws the Loans tab: "My current loan" repayment calculator and "Can I afford a loan?".
// All the maths lives in loan-calc.js (window.LoanCalc). Section 2 also asks the backend's AI model (POST /api/loans/predict).
// Graphs use Chart.js from a CDN; when offline it isn't loaded, so the graphs are hidden instead.
// Texts come from i18n.js: t("key"). A language switch calls redrawLoans() to redo the shown results.

// ===== STATE =====
const LOAN_MAX_AMOUNT = 100000000; // Rs 10 crore: biggest loan / income we accept
const LOAN_MAX_RATE = 100;         // % a year
const loanCharts = {};             // open Chart.js graphs by canvas id, so we can redraw them
let existingWasAutoFilled = false; // true while "existing repayments" holds the value copied from section 1
let lastAffordability = null;      // { answer, v } of the last "Can I afford" result, to redraw it in another language

// ===== HELPERS =====
// Reads all fields of a form. specs = [[inputId, options], ...] (options.label = a translation key).
// Returns values by id, or null + shows the first error (translated from LoanCalc's error code).
function readLoanFields(specs, messageId) {
  const values = {};
  for (const [id, options] of specs) {
    const result = LoanCalc.checkNumber(byId(id).value, options);
    if (result.error) {
      const text = t("loan.error." + result.code, { field: t(options.label) });
      byId(messageId).textContent = text.charAt(0).toUpperCase() + text.slice(1); // "the age…" → "The age…"
      byId(id).focus();
      return null;
    }
    values[id] = result.value;
  }
  byId(messageId).textContent = "";
  return values;
}

// Draws (or redraws) one graph. Without Chart.js (offline) it shows the "need internet" note instead.
function drawLoanChart(canvasId, config) {
  const canvas = byId(canvasId);
  const offlineNote = canvas.closest("section").querySelector(".chart-offline");
  if (typeof Chart === "undefined") {
    canvas.parentElement.hidden = true;
    offlineNote.hidden = false;
    return;
  }
  offlineNote.hidden = true;
  canvas.parentElement.hidden = false;
  if (loanCharts[canvasId]) loanCharts[canvasId].destroy(); // remove the old graph first
  loanCharts[canvasId] = new Chart(canvas, config);
}

// 40 → "3 years 4 months" in the current language (LoanCalc.formatDuration is English only)
function formatLoanDuration(months) {
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [];
  if (years) parts.push(t(years === 1 ? "loan.year" : "loan.years", { n: years }));
  if (rest || !years) parts.push(t(rest === 1 ? "loan.month" : "loan.months", { n: rest }));
  return parts.join(" ");
}

// Shared look for the graphs (matches the dark theme in style.css)
function loanChartOptions(xTitle) {
  const grid = { color: "rgba(160, 190, 255, 0.12)" };
  const ticks = { color: "#9fb0d6", maxTicksLimit: 6 };
  return {
    responsive: true,
    maintainAspectRatio: false, // fill the .chart-box height
    animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: "#e8eeff", boxWidth: 12 } },
      tooltip: { callbacks: { label: (c) => c.dataset.label + ": " + LoanCalc.formatRupees(c.parsed.y) } },
    },
    scales: {
      x: { grid: grid, ticks: ticks, title: { display: true, text: xTitle, color: "#9fb0d6" } },
      y: { grid: grid, ticks: { ...ticks, callback: (v) => LoanCalc.formatRupees(v).replace("Rs ", "") } },
    },
  };
}

// ===== SECTION 1: MY CURRENT LOAN =====
function calculateRepayment(event) {
  event.preventDefault(); // stay on the page
  const v = readLoanFields([
    ["repay-balance", { label: "loan.field.balance", max: LOAN_MAX_AMOUNT }],
    ["repay-rate", { label: "loan.field.rate", allowZero: true, max: LOAN_MAX_RATE }],
    ["repay-payment", { label: "loan.field.payment", max: LOAN_MAX_AMOUNT }],
    ["repay-extra", { label: "loan.field.extra", required: false, allowZero: true, max: LOAN_MAX_AMOUNT }],
  ], "repay-msg");
  if (!v) return;

  const result = LoanCalc.compareExtra(v["repay-balance"], v["repay-rate"], v["repay-payment"], v["repay-extra"]);
  const plan = result.normal;
  byId("repay-result").hidden = false;
  const warning = byId("repay-warning");

  if (!plan.ok) {
    // Show a warning instead of numbers
    byId("repay-numbers").hidden = true;
    warning.hidden = false;
    warning.textContent = plan.reason === "payment-too-low"
      ? "⚠ " + t("loan.paymentTooLow", { payment: LoanCalc.formatRupees(v["repay-payment"]),
        interest: LoanCalc.formatRupees(plan.monthlyInterest), minimum: LoanCalc.formatRupees(Math.ceil(plan.monthlyInterest)) })
      : "⚠ " + t("loan.tooLong");
    return;
  }
  warning.hidden = true;
  byId("repay-numbers").hidden = false;

  // Payoff date counts from the start date, or today if it's empty or already passed
  const typedStart = byId("repay-start").value ? new Date(byId("repay-start").value + "T00:00") : null;
  const today = new Date();
  const start = typedStart && typedStart > today ? typedStart : today;
  const payoff = LoanCalc.addMonths(start, plan.months);

  byId("repay-time").textContent = formatLoanDuration(plan.months);
  byId("repay-date").textContent = I18n.formatDate(payoff, { month: "short", year: "numeric" });
  byId("repay-interest").textContent = LoanCalc.formatRupees(plan.totalInterest);
  byId("repay-total").textContent = LoanCalc.formatRupees(plan.totalPaid);

  // Extra payment comparison
  const extraText = byId("repay-extra-text");
  const extraPlan = result.withExtra;
  extraText.hidden = !extraPlan;
  if (extraPlan) {
    extraText.textContent = t("loan.extraResult", { extra: LoanCalc.formatRupees(v["repay-extra"]),
      sooner: formatLoanDuration(result.monthsSooner), total: formatLoanDuration(extraPlan.months),
      saved: LoanCalc.formatRupees(result.interestSaved) });
  }

  // Line graph: remaining balance each month (+ the extra-payment line)
  const datasets = [{ label: t("loan.chart.balance"), data: plan.balances, borderColor: "#3d8bff", backgroundColor: "rgba(61, 139, 255, 0.18)", fill: true, pointRadius: 0, tension: 0.2 }];
  if (extraPlan) datasets.push({ label: t("loan.chart.withExtra"), data: extraPlan.balances, borderColor: "#3ddc84", pointRadius: 0, tension: 0.2 });
  drawLoanChart("repay-chart", {
    type: "line",
    data: { labels: plan.balances.map((_, month) => month), datasets: datasets },
    options: loanChartOptions(t("loan.chart.month")),
  });

  // Donut: how much of what you pay is the loan itself vs interest
  drawLoanChart("split-chart", {
    type: "doughnut",
    data: {
      labels: [t("loan.chart.loanAmount"), t("loan.chart.interest")],
      datasets: [{ data: [v["repay-balance"], plan.totalInterest], backgroundColor: ["#3d8bff", "#ff9a4a"], borderWidth: 0 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { position: "right", labels: { color: "#e8eeff", boxWidth: 12 } },
        tooltip: { callbacks: { label: (c) => c.label + ": " + LoanCalc.formatRupees(c.parsed) } },
      },
    },
  });

  // Pre-fill "existing repayments" in section 2 (unless the user typed their own number there)
  const existing = byId("afford-existing");
  if (existing.value === "" || existingWasAutoFilled) {
    existing.value = v["repay-payment"];
    existingWasAutoFilled = true;
  }
}

// ===== SECTION 2: HOW MUCH CAN I BORROW? (AI model on the backend) =====
// Fills income and expenses from this month's Money tab (only empty boxes, or ones we filled before).
async function prefillLoanFromMoney() {
  try {
    const summary = await getSummary(getThisMonthText()); // in api.js / app.js
    fillIfFree("afford-income", summary.income);
    fillIfFree("afford-expenses", summary.spent);
  } catch (error) {
    // No Money data (e.g. offline): the user just types the numbers
  }
}

function fillIfFree(id, amount) {
  const input = byId(id);
  if (!(amount > 0)) return;
  if (input.value === "" || input.dataset.autoFilled === "yes") {
    input.value = Math.round(amount);
    input.dataset.autoFilled = "yes"; // cleared when the user types (see START)
  }
}

// Green under 30%, amber 30–40%, red above 40% (same limits as the backend verdict)
function ratioLevel(ratio) {
  if (ratio < 0.3) return "good";
  if (ratio <= LoanCalc.MAX_DEBT_TO_INCOME) return "warn";
  return "over";
}

async function calculateAffordability(event) {
  event.preventDefault();
  const v = readLoanFields([
    ["afford-income", { label: "loan.field.income", max: LOAN_MAX_AMOUNT }],
    ["afford-expenses", { label: "loan.field.expenses", required: false, allowZero: true, max: LOAN_MAX_AMOUNT }],
    ["afford-existing", { label: "loan.field.existing", required: false, allowZero: true, max: LOAN_MAX_AMOUNT }],
    ["afford-credit", { label: "loan.field.credit", whole: true }],
    ["afford-age", { label: "loan.field.age", whole: true }],
    ["afford-rate", { label: "loan.field.rate", allowZero: true, max: LOAN_MAX_RATE }],
    ["afford-years", { label: "loan.field.years", max: 30, whole: true }],
  ], "afford-msg");
  if (!v) return;

  const button = byId("afford-form").querySelector("button[type=submit]");
  button.disabled = true;
  let answer;
  try {
    answer = await predictLoan({
      monthly_income: v["afford-income"], monthly_expenses: v["afford-expenses"] || 0,
      existing_debt_payment: v["afford-existing"] || 0, credit_score: v["afford-credit"], age: v["afford-age"],
      interest_rate: v["afford-rate"], years: v["afford-years"],
    });
  } catch (error) {
    byId("afford-msg").textContent = error.message; // friendly message from the backend (or "no internet")
    return;
  } finally {
    button.disabled = false;
  }
  showAffordability(answer, v);
}

// answer = the backend reply; v = the typed numbers
function showAffordability(answer, v) {
  lastAffordability = { answer: answer, v: v };
  const amount = Number(answer.predicted_max_loan) || 0; // never NaN on screen
  const ratio = Number(answer.debt_to_income_ratio) || 0;
  const level = ratioLevel(ratio);
  byId("afford-result").hidden = false;
  const warning = byId("afford-warning");
  warning.hidden = amount > 0;
  warning.textContent = t("loan.noRoom");

  byId("afford-ai").textContent = t(answer.source === "ai" ? "loan.aiEstimate" : "loan.estimate",
    { amount: LoanCalc.formatRupees(amount) });
  byId("afford-dti-text").textContent = Math.round(ratio * 100) + "%";
  const bar = byId("afford-dti-bar");
  bar.className = "bar " + level;
  bar.firstElementChild.style.width = Math.min(ratio * 100, 100) + "%";
  bar.setAttribute("aria-valuenow", Math.round(ratio * 100));
  const verdict = byId("afford-verdict");
  verdict.className = "afford-verdict " + level;
  verdict.textContent = t("loan.verdict." + level); // same limits as the backend's English verdict
  byId("afford-formula").textContent = t("loan.formula", { limit: Math.round(LoanCalc.MAX_DEBT_TO_INCOME * 100),
    rate: v["afford-rate"], years: v["afford-years"], amount: LoanCalc.formatRupees(answer.formula_max_loan) })
    + (answer.source === "ai" ? "" : " " + t("loan.aiUnavailable"));

  // Monthly repayment for the estimated amount at the chosen rate and term
  const plan = LoanCalc.repaymentFor(amount, v["afford-rate"], v["afford-years"]);
  byId("afford-max").textContent = LoanCalc.formatRupees(amount);
  byId("afford-payment").textContent = t("common.perMonth", { amount: LoanCalc.formatRupees(plan.payment) });
  byId("afford-interest").textContent = LoanCalc.formatRupees(plan.totalInterest);
  byId("afford-total").textContent = LoanCalc.formatRupees(plan.totalRepaid);

  // Graph: standard-rule max loan for each term (1–25 years) vs the AI estimate (which doesn't depend on term)
  const curve = LoanCalc.borrowCurve(Number(answer.formula_monthly_payment) || 0, v["afford-rate"]);
  drawLoanChart("afford-chart", {
    type: "line",
    data: {
      labels: curve.map((p) => p.years),
      datasets: [
        { label: t("loan.chart.standardRule"), data: curve.map((p) => p.amount), borderColor: "#38d6ff", backgroundColor: "rgba(56, 214, 255, 0.16)", fill: true, pointRadius: 2, tension: 0.2 },
        { label: t("loan.chart.aiEstimate"), data: curve.map(() => amount), borderColor: "#3ddc84", borderDash: [6, 4], pointRadius: 0 },
      ],
    },
    options: loanChartOptions(t("loan.chart.termYears")),
  });
}

// ===== LANGUAGE SWITCH (called by app.js) =====
// Redo the results already on screen so their texts, dates and graph labels use the new language
function redrawLoans() {
  if (!byId("repay-result").hidden) calculateRepayment({ preventDefault() {} });
  if (!byId("afford-result").hidden && lastAffordability) {
    showAffordability(lastAffordability.answer, lastAffordability.v);
  }
}

// ===== START =====
byId("repay-form").addEventListener("submit", calculateRepayment);
byId("afford-form").addEventListener("submit", calculateAffordability);
byId("afford-existing").addEventListener("input", () => (existingWasAutoFilled = false)); // user typed their own value
["afford-income", "afford-expenses"].forEach((id) => byId(id).addEventListener("input", () => delete byId(id).dataset.autoFilled));
