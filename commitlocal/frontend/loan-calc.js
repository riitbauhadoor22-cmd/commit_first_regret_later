// loan-calc.js — all the loan maths as plain functions (no page, no network).
// Works in the browser (window.LoanCalc) and in Node for tests (require("../../frontend/loan-calc.js")).
// Every function returns plain numbers / objects and never returns NaN or loops forever.

(function () {
  // ===== SETTINGS (easy to change) =====
  const MAX_DEBT_TO_INCOME = 0.4; // banks usually allow up to 40% of monthly income for ALL loan repayments
  const MAX_MONTHS = 1200;        // stop after 100 years: treat as "never paid off"
  const CURVE_YEARS = 25;         // the "max borrowable vs term" graph goes from 1 to 25 years

  // ===== HELPERS =====
  // 12 (% a year) → 0.01 (per month). Monthly compounding.
  function monthlyRate(annualPercent) {
    return annualPercent > 0 ? annualPercent / 100 / 12 : 0; // negative or missing rate counts as 0%
  }

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  // 12345.6 → "Rs 12,346" (whole rupees, shared formatter in i18n.js). Bad input → "Rs 0", never "Rs NaN".
  function formatRupees(amount) {
    // Whole rupees through the shared formatter (i18n.js) when it's loaded; same "Rs 12,345" shape in Node tests
    const shared = typeof I18n !== "undefined" ? I18n : (typeof require === "function" ? require("./i18n.js") : null);
    return shared.formatMoney(amount, { whole: true });
  }

  // 40 → "3 years 4 months"
  function formatDuration(months) {
    const years = Math.floor(months / 12);
    const rest = months % 12;
    const parts = [];
    if (years) parts.push(years + (years === 1 ? " year" : " years"));
    if (rest || !years) parts.push(rest + (rest === 1 ? " month" : " months"));
    return parts.join(" ");
  }

  // Date + n months (keeps the day where possible, e.g. 31 Jan + 1 month → 28/29 Feb)
  function addMonths(date, months) {
    const d = new Date(date.getFullYear(), date.getMonth() + months, 1);
    const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    d.setDate(Math.min(date.getDate(), lastDay));
    return d;
  }

  // Checks one typed value. Returns { value } or { error, code } (English text + a code loans-tab.js translates).
  // options: label, required (default true), allowZero, max, whole (whole numbers only)
  function checkNumber(text, options) {
    const label = options.label;
    const t = String(text == null ? "" : text).trim();
    if (t === "") {
      if (options.required === false) return { value: 0 };
      return { error: "Please enter " + label + ".", code: "required" };
    }
    const n = Number(t);
    if (!isFinite(n)) return { error: label[0].toUpperCase() + label.slice(1) + " must be a number.", code: "notNumber" };
    if (n < 0) return { error: label[0].toUpperCase() + label.slice(1) + " can't be negative.", code: "negative" };
    if (n === 0 && !options.allowZero) return { error: label[0].toUpperCase() + label.slice(1) + " must be more than 0.", code: "zero" };
    if (options.max != null && n > options.max) return { error: label[0].toUpperCase() + label.slice(1) + " is too big.", code: "tooBig" };
    if (options.whole && !Number.isInteger(n)) return { error: label[0].toUpperCase() + label.slice(1) + " must be a whole number.", code: "notWhole" };
    return { value: n };
  }

  // ===== SECTION 1: REPAYING A LOAN =====
  // Month-by-month amortisation. Each month: balance grows by interest, then the payment comes off.
  // Returns { ok: true, months, totalInterest, totalPaid, balances: [start, after month 1, ...] }
  // or { ok: false, reason: "payment-too-low", monthlyInterest } / { ok: false, reason: "too-long" }.
  function repaymentPlan(balance, annualPercent, payment) {
    const r = monthlyRate(annualPercent);
    balance = Math.max(0, balance || 0); // a negative balance means nothing is owed
    const firstInterest = balance * r;
    // If the payment can't even cover the first month's interest, the balance never goes down
    if (payment <= firstInterest) return { ok: false, reason: "payment-too-low", monthlyInterest: firstInterest };

    let left = balance;
    let totalInterest = 0;
    let totalPaid = 0;
    const balances = [round2(left)];
    let months = 0;
    while (left > 0.005) { // stop when less than half a paisa is left
      if (months >= MAX_MONTHS) return { ok: false, reason: "too-long" };
      const interest = left * r;
      const pay = Math.min(payment, left + interest); // last payment is only what's left
      totalInterest += interest;
      totalPaid += pay;
      left = left + interest - pay;
      months += 1;
      balances.push(round2(Math.max(left, 0)));
    }
    return { ok: true, months, totalInterest: round2(totalInterest), totalPaid: round2(totalPaid), balances };
  }

  // Normal plan + plan with an extra payment every month, and what the extra saves.
  function compareExtra(balance, annualPercent, payment, extra) {
    const normal = repaymentPlan(balance, annualPercent, payment);
    if (!normal.ok || !(extra > 0)) return { normal, withExtra: null };
    const withExtra = repaymentPlan(balance, annualPercent, payment + extra);
    return {
      normal,
      withExtra,
      monthsSooner: normal.months - withExtra.months,
      interestSaved: round2(normal.totalInterest - withExtra.totalInterest),
    };
  }

  // ===== SECTION 2: HOW MUCH CAN I BORROW? =====
  // Present value: the loan that a fixed monthly payment pays off exactly in `years`.
  function maxBorrowable(payment, annualPercent, years) {
    const n = Math.round(years * 12);
    const r = monthlyRate(annualPercent);
    if (payment <= 0 || n <= 0) return 0;
    if (r === 0) return payment * n; // 0% interest: just payment × months
    return (payment * (1 - Math.pow(1 + r, -n))) / r;
  }

  // Returns { ok: false, limit, existing, affordable } when no room for a new loan,
  // or { ok: true, limit, payment, maxLoan, totalRepaid, totalInterest }.
  function affordability(income, existing, annualPercent, years) {
    const limit = Math.max(0, income || 0) * MAX_DEBT_TO_INCOME; // most you should spend on all repayments a month
    const affordable = limit - existing;
    if (affordable <= 0) return { ok: false, limit: round2(limit), existing, affordable: round2(affordable) };
    const maxLoan = maxBorrowable(affordable, annualPercent, years);
    const totalRepaid = affordable * Math.round(years * 12);
    return {
      ok: true,
      limit: round2(limit),
      payment: round2(affordable),
      maxLoan: round2(maxLoan),
      totalRepaid: round2(totalRepaid),
      totalInterest: round2(totalRepaid - maxLoan),
    };
  }

  // Monthly repayment (EMI) that pays off `amount` in `years` — the reverse of maxBorrowable.
  // Returns { payment, totalRepaid, totalInterest }; bad input → zeros, never NaN.
  function repaymentFor(amount, annualPercent, years) {
    const n = Math.round(years * 12);
    const r = monthlyRate(annualPercent);
    if (!(amount > 0) || !(n > 0) || !(r >= 0)) return { payment: 0, totalRepaid: 0, totalInterest: 0 };
    const payment = r === 0 ? amount / n : (amount * r) / (1 - Math.pow(1 + r, -n));
    return { payment: round2(payment), totalRepaid: round2(payment * n), totalInterest: round2(payment * n - amount) };
  }

  // [{ years: 1, amount }, ... { years: 25, amount }] for the graph
  function borrowCurve(payment, annualPercent) {
    const points = [];
    for (let y = 1; y <= CURVE_YEARS; y++) points.push({ years: y, amount: round2(maxBorrowable(payment, annualPercent, y)) });
    return points;
  }

  // ===== EXPORT =====
  const LoanCalc = {
    MAX_DEBT_TO_INCOME, MAX_MONTHS, CURVE_YEARS,
    monthlyRate, formatRupees, formatDuration, addMonths, checkNumber,
    repaymentPlan, compareExtra, maxBorrowable, affordability, borrowCurve, repaymentFor,
  };
  if (typeof window !== "undefined") window.LoanCalc = LoanCalc; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = LoanCalc; // Node tests
})();
