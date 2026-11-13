// budget-calc.test.js — tests for frontend/budget-calc.js. Run: node --test tests/frontend
const test = require("node:test");
const assert = require("node:assert/strict");
const B = require("../../frontend/budget-calc.js");

// ===== NO BUDGET / MISSING VALUES =====
test("no budget: only spent, no bar, level none", () => {
  for (const budget of [null, undefined, 0, "", NaN, -100]) {
    const p = B.budgetProgress(190, budget);
    assert.deepEqual(p, { spent: 190, budget: 0, hasBudget: false, percent: 0, barPercent: 0, left: 0, over: 0, level: "none" });
  }
});

test("missing spent counts as 0 and never gives NaN", () => {
  const p = B.budgetProgress(undefined, 5000);
  assert.equal(p.spent, 0);
  assert.equal(p.left, 5000);
  assert.equal(p.level, "ok");
  Object.values(p).forEach((v) => assert.ok(!Number.isNaN(v)));
});

// ===== UNDER / AT / OVER =====
test("under budget: Rs 3,200 of Rs 5,000 leaves Rs 1,800", () => {
  const p = B.budgetProgress(3200, 5000);
  assert.equal(p.percent, 64);
  assert.equal(p.left, 1800);
  assert.equal(p.over, 0);
  assert.equal(p.level, "ok");
});

test("exactly at budget: 100%, nothing left, not over", () => {
  const p = B.budgetProgress(5000, 5000);
  assert.equal(p.percent, 100);
  assert.equal(p.left, 0);
  assert.equal(p.over, 0);
  assert.equal(p.level, "warn");
});

test("over budget: Rs 700 over, bar capped at 100%", () => {
  const p = B.budgetProgress(5700, 5000);
  assert.equal(p.over, 700);
  assert.equal(p.left, 0);
  assert.equal(p.percent, 114);
  assert.equal(p.barPercent, 100);
  assert.equal(p.level, "over");
});

test("paise are kept without float noise", () => {
  assert.equal(B.budgetProgress(100.1, 200.3).left, 100.2);
});

// ===== COLOUR THRESHOLDS =====
test("colour thresholds: 79% ok, 80% warn, 100% warn, 101% over", () => {
  assert.equal(B.budgetProgress(79, 100).level, "ok");
  assert.equal(B.budgetProgress(80, 100).level, "warn");
  assert.equal(B.budgetProgress(100, 100).level, "warn");
  assert.equal(B.budgetProgress(101, 100).level, "over");
  assert.equal(B.budgetProgress(4000, 5000).level, "warn"); // 80% with bigger numbers
  assert.equal(B.budgetProgress(3999.99, 5000).level, "ok");
});
