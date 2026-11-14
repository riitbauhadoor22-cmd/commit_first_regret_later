// category-guess.test.js — tests for frontend/category-guess.js (offline keyword guess for the expense category).
// Run: node --test tests/frontend/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../frontend/category-guess.js");

const KEYWORDS = { "Groceries": ["Winners", "Super U"], "Food & drinks": ["KFC", "McDonald's", "dholl puri"],
  "Transport": ["bus", "metro", "Metro Express"], "Subscriptions": ["my.t"], "Utilities": ["CEB"] };

test("keywords find the category", () => {
  assert.equal(G.matchKeywords("KFC 350", KEYWORDS), "Food & drinks");
  assert.equal(G.matchKeywords("Winners groceries", KEYWORDS), "Groceries");
  assert.equal(G.matchKeywords("super u", KEYWORDS), "Groceries");
  assert.equal(G.matchKeywords("my.t box", KEYWORDS), "Subscriptions");
});

test("case, accents and punctuation don't matter; whole words only", () => {
  assert.equal(G.normalise("Dholl Purî!"), "dholl puri");
  assert.equal(G.matchKeywords("DHOLL PURÎ", KEYWORDS), "Food & drinks");
  assert.equal(G.matchKeywords("mcdonalds", KEYWORDS), "Food & drinks");
  assert.equal(G.matchKeywords("CÉB", KEYWORDS), "Utilities");
  assert.equal(G.matchKeywords("busy", KEYWORDS), null);
});

test("no match, empty text or no list → null (the form is left as it is)", () => {
  assert.equal(G.matchKeywords("something 120", KEYWORDS), null);
  assert.equal(G.matchKeywords("", KEYWORDS), null);
  assert.equal(G.matchKeywords("KFC", null), null);
});
