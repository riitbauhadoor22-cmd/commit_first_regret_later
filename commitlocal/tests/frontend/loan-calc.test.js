// loan-calc.test.js — tests for frontend/loan-calc.js. Run: node --test tests/frontend
const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../../frontend/loan-calc.js");

const near = (a, b, tol = 1) => assert.ok(Math.abs(a - b) <= tol, a + " is not close to " + b);

// ===== REPAYMENT PLAN =====
test("standard loan: 1,00,000 at 12% paying the 12-month EMI takes 12 months", () => {
  const plan = L.repaymentPlan(100000, 12, 8884.88); // known EMI for 12 months at 1%/month
  assert.equal(plan.ok, true);
  assert.equal(plan.months, 12);
  near(plan.totalInterest, 6618.55, 1);
  near(plan.totalPaid, 106618.55, 1);
  assert.equal(plan.balances.length, 13); // start + 12 months
  assert.equal(plan.balances[12], 0);
});

test("0% interest: months = ceil(balance / payment), no interest", () => {
  const plan = L.repaymentPlan(10000, 0, 3000);
  assert.equal(plan.months, 4);
  assert.equal(plan.totalInterest, 0);
  assert.equal(plan.totalPaid, 10000);
});

test("payment too low to cover interest → warning, not a loop", () => {
  const plan = L.repaymentPlan(100000, 12, 1000); // interest is exactly 1000 a month
  assert.equal(plan.ok, false);
  assert.equal(plan.reason, "payment-too-low");
  assert.equal(plan.monthlyInterest, 1000);
  assert.equal(L.repaymentPlan(100000, 12, 500).ok, false);
});

test("payment just above interest but over 100 years → too-long", () => {
  const plan = L.repaymentPlan(100000, 12, 1000.001); // ~1,388 months
  assert.equal(plan.ok, false);
  assert.equal(plan.reason, "too-long");
});

test("extra payment finishes sooner and saves interest", () => {
  const c = L.compareExtra(100000, 12, 2000, 1000);
  assert.ok(c.monthsSooner > 0);
  assert.ok(c.interestSaved > 0);
  assert.equal(c.withExtra.months + c.monthsSooner, c.normal.months);
  assert.equal(L.compareExtra(100000, 12, 2000, 0).withExtra, null);
});

// ===== AFFORDABILITY =====
test("max borrowable = present value of payment", () => {
  near(L.maxBorrowable(8884.88, 12, 1), 100000, 1);
  assert.equal(L.maxBorrowable(1000, 0, 2), 24000); // 0%: payment × months
  assert.equal(L.maxBorrowable(0, 10, 5), 0);
});

test("affordability uses 40% of income minus existing repayments", () => {
  const a = L.affordability(50000, 5000, 0, 1);
  assert.equal(a.ok, true);
  assert.equal(a.payment, 15000); // 20,000 − 5,000
  assert.equal(a.maxLoan, 180000);
  assert.equal(a.totalInterest, 0);
});

test("zero income → can't borrow", () => {
  const a = L.affordability(0, 0, 10, 5);
  assert.equal(a.ok, false);
  assert.equal(a.limit, 0);
});

test("existing repayments already at the limit → can't borrow", () => {
  assert.equal(L.affordability(30000, 12000, 10, 5).ok, false);
});

test("borrow curve has 25 points that grow with the term", () => {
  const curve = L.borrowCurve(5000, 10);
  assert.equal(curve.length, 25);
  assert.ok(curve[24].amount > curve[0].amount);
});

// ===== FORMATTING + VALIDATION =====
test("formatRupees never shows NaN", () => {
  assert.equal(L.formatRupees(12345.4), "Rs 12,345");
  assert.equal(L.formatRupees(NaN), "Rs 0");
  assert.equal(L.formatRupees(Infinity), "Rs 0");
});

test("formatDuration", () => {
  assert.equal(L.formatDuration(40), "3 years 4 months");
  assert.equal(L.formatDuration(12), "1 year");
  assert.equal(L.formatDuration(1), "1 month");
});

test("checkNumber rejects empty, negative and text", () => {
  assert.ok(L.checkNumber("", { label: "the amount" }).error);
  assert.ok(L.checkNumber("-5", { label: "the amount" }).error);
  assert.ok(L.checkNumber("abc", { label: "the amount" }).error);
  assert.ok(L.checkNumber("0", { label: "the amount" }).error);
  assert.equal(L.checkNumber("0", { label: "the rate", allowZero: true }).value, 0);
  assert.equal(L.checkNumber("", { label: "extra", required: false }).value, 0);
  assert.ok(L.checkNumber("2.5", { label: "the term", whole: true }).error);
});

test("addMonths handles month ends", () => {
  const d = L.addMonths(new Date(2025, 0, 31), 1);
  assert.equal(d.getMonth(), 1);
  assert.equal(d.getDate(), 28);
});

// ===== REPAYMENT FOR AN AMOUNT (used with the AI estimate) =====
test("repaymentFor: 1,00,000 at 12% over 1 year is the known EMI 8,884.88", () => {
  const r = L.repaymentFor(100000, 12, 1);
  near(r.payment, 8884.88, 0.01);
  near(r.totalInterest, 6618.6, 0.5);
});

test("repaymentFor: 0% interest splits evenly; bad input gives zeros, not NaN", () => {
  assert.equal(L.repaymentFor(12000, 0, 1).payment, 1000);
  assert.deepEqual(L.repaymentFor(NaN, 10, 5), { payment: 0, totalRepaid: 0, totalInterest: 0 });
  assert.deepEqual(L.repaymentFor(0, 10, 5), { payment: 0, totalRepaid: 0, totalInterest: 0 });
});

// ===== EDGE CASES (full test pass) =====
test("zero balance: already paid off, 0 months, no NaN", () => {  // nothing to repay
  const plan = L.repaymentPlan(0, 10, 100);
  assert.equal(plan.ok, true);
  assert.equal(plan.months, 0);
  assert.equal(plan.totalInterest, 0);
});

test("zero or negative payment → payment-too-low, never an endless loop", () => {
  assert.equal(L.repaymentPlan(1000, 10, 0).reason, "payment-too-low");
  assert.equal(L.repaymentPlan(1000, 10, -5).reason, "payment-too-low");
  assert.equal(L.repaymentPlan(1000, 0, 0).reason, "payment-too-low"); // 0% and 0 payment too
});

test("negative extra payment is ignored (no 'with extra' plan)", () => {
  assert.equal(L.compareExtra(1000, 0, 100, -5).withExtra, null);
});

test("payoff date: 12 months from 31 Jan 2026 is 31 Jan 2027", () => {
  const date = L.addMonths(new Date(2026, 0, 31), 12);
  assert.deepEqual([date.getFullYear(), date.getMonth(), date.getDate()], [2027, 0, 31]);
});

test("the form's checkNumber blocks 0 balance, negative rate and text before any maths runs", () => {
  assert.equal(L.checkNumber("0", { label: "x" }).code, "zero");
  assert.equal(L.checkNumber("-1", { label: "x", allowZero: true }).code, "negative");
  assert.equal(L.checkNumber("1e20", { label: "x", max: 10000000 }).code, "tooBig");
  assert.equal(L.checkNumber("abc", { label: "x" }).code, "notNumber");
});

test("negative income → can't borrow, max borrowable never negative", () => {
  assert.equal(L.affordability(-100, 0, 10, 5).ok, false);
  assert.equal(L.maxBorrowable(-5, 10, 5), 0);
});
