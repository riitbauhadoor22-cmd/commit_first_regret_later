// game-calc.js — live maths for the Budget Challenge form (Arcade): totals, money left and the Needs/Wants/Savings split.
// Only for showing numbers while typing — the real score is always worked out on the server (backend/game_logic.py).
// No screen code here, so the same file runs in the browser and in Node tests (tests/frontend).
(function () {
  // Anything that isn't a real number ≥ 0 (null, "", NaN, text, negative) counts as 0 → never NaN on screen
  function toAmount(value) {
    if (value === null || value === undefined || value === "") return 0;
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
  }

  // True when a typed value is a problem (text, negative, too big). Empty is fine (= Rs 0).
  function isBadAmount(value) {
    if (value === null || value === undefined || String(value).trim() === "") return false;
    const number = Number(value);
    return !Number.isFinite(number) || number < 0 || number > 10000000;
  }

  // categories: [{id, kind}], values: {id: typed value}, income: rupees. Adds up in whole cents (no 0.1 + 0.2 drift).
  // kind "savings" = the Savings & debt group (loan repayments count there).
  function allocationTotals(categories, values, income) {
    const cents = { need: 0, want: 0, savings: 0 };
    let totalCents = 0;
    (categories || []).forEach((category) => {
      const amount = Math.round(toAmount((values || {})[category.id]) * 100);
      if (category.kind in cents) cents[category.kind] += amount;
      totalCents += amount;
    });
    const incomeCents = Math.round(toAmount(income) * 100);
    const percent = (part) => (incomeCents > 0 ? (part / incomeCents) * 100 : 0);
    return {
      total: totalCents / 100,
      left: (incomeCents - totalCents) / 100, // negative = over income
      needs: percent(cents.need),
      wants: percent(cents.want),
      savings: percent(cents.savings),
      amounts: { need: cents.need / 100, want: cents.want / 100, savings: cents.savings / 100 },
    };
  }

  // Server times are UTC without a zone ("2026-11-13T22:10:00") -> a Date, so it shows in the phone's local time
  function parseUtc(text) {
    if (!text) return null;
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(text) ? text : text + "Z");
    return Number.isNaN(date.getTime()) ? null : date;
  }

  // Bar widths in %: squeezed to fit when the three add up to more than 100 (same as the Money tab bar)
  function barWidths(needs, wants, savings) {
    const total = Math.max(needs + wants + savings, 100);
    return { needs: (needs / total) * 100, wants: (wants / total) * 100, savings: (savings / total) * 100 };
  }

  const GameCalc = { toAmount, isBadAmount, allocationTotals, barWidths, parseUtc };
  if (typeof window !== "undefined") window.GameCalc = GameCalc; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = GameCalc; // Node tests
})();
