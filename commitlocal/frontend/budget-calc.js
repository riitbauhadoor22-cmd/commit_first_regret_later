// budget-calc.js — the "spent vs budget" maths for each spending category (Money out tab).
// No screen code here, so the same file runs in the browser and in Node tests (tests/frontend).
(function () {
  const WARN_PERCENT = 80; // from 80% of the budget the bar turns amber

  // Anything that isn't a real positive number (null, undefined, NaN, "", negative) counts as 0
  function toAmount(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
  }

  const round2 = (n) => Math.round(n * 100) / 100; // rupees with paise

  // spent + budget → numbers for the row / sheet. budget 0 or missing = "no budget set".
  // level: "none" (no budget), "ok" (< 80%), "warn" (80–100%), "over" (> 100%)
  function budgetProgress(spent, budget) {
    const s = toAmount(spent);
    const b = toAmount(budget);
    if (b === 0) {
      return { spent: s, budget: 0, hasBudget: false, percent: 0, barPercent: 0, left: 0, over: 0, level: "none" };
    }
    const percent = Math.round((s / b) * 1000) / 10; // 1 decimal
    let level = "ok";
    if (s > b) level = "over";
    else if (s * 100 >= WARN_PERCENT * b) level = "warn"; // multiply instead of divide: no rounding surprises
    return {
      spent: s, budget: b, hasBudget: true, percent: percent,
      barPercent: Math.min(percent, 100), // the bar never grows wider than its box
      left: round2(Math.max(b - s, 0)),
      over: round2(Math.max(s - b, 0)),
      level: level,
    };
  }

  const BudgetCalc = { WARN_PERCENT, toAmount, budgetProgress };
  if (typeof window !== "undefined") window.BudgetCalc = BudgetCalc; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = BudgetCalc; // Node tests
})();
