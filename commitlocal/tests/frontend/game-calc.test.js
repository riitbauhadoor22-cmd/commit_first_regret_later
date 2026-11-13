// game-calc.test.js — tests for frontend/game-calc.js (Budget Challenge live totals) and that every level, category
// and event id in backend/game/scenarios.py has a text in en.json. Run: node --test tests/frontend
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const G = require("../../frontend/game-calc.js");

const CATS = [{ id: "food", kind: "need" }, { id: "fun", kind: "want" }, { id: "savings", kind: "savings" }];

// ===== AMOUNTS =====
test("bad or empty values count as 0, never NaN", () => {
  for (const value of [null, undefined, "", "abc", NaN, -5, Infinity]) assert.equal(G.toAmount(value), 0);
  assert.equal(G.toAmount("1200.5"), 1200.5);
});

test("isBadAmount: empty is fine, text / negative / huge are not", () => {
  for (const value of ["", null, "0", "3000"]) assert.equal(G.isBadAmount(value), false, String(value));
  for (const value of ["abc", "-1", "1e20"]) assert.equal(G.isBadAmount(value), true, value);
});

// ===== TOTALS AND SPLIT =====
test("totals, money left and 50/30/20 percents", () => {
  const r = G.allocationTotals(CATS, { food: "4000", fun: "2400", savings: "1600" }, 8000);
  assert.deepEqual(r, { total: 8000, left: 0, needs: 50, wants: 30, savings: 20,
    amounts: { need: 4000, want: 2400, savings: 1600 } });
  const paise = G.allocationTotals(CATS, { food: "0.1", fun: "0.2" }, 1);
  assert.equal(paise.left, 0.7); // added up in cents: no 0.30000000000000004
  const over = G.allocationTotals(CATS, { food: "9000" }, 8000);
  assert.equal(over.left, -1000);
});

test("missing values or income never give NaN", () => {
  const r = G.allocationTotals(CATS, undefined, undefined);
  for (const value of Object.values(r).concat(Object.values(r.amounts))) if (typeof value !== "object") assert.ok(Number.isFinite(value));
});

test("bar widths squeeze to 100% when over", () => {
  assert.deepEqual(G.barWidths(50, 30, 20), { needs: 50, wants: 30, savings: 20 });
  const w = G.barWidths(100, 50, 50);
  assert.equal(w.needs + w.wants + w.savings, 100);
});

test("parseUtc reads server UTC times (local display), bad / empty -> null", () => {
  assert.equal(G.parseUtc("2026-11-13T22:10:00").toISOString(), "2026-11-13T22:10:00.000Z");
  assert.equal(G.parseUtc("2026-11-13T22:10:00+00:00").toISOString(), "2026-11-13T22:10:00.000Z");
  for (const bad of [null, "", "abc"]) assert.equal(G.parseUtc(bad), null);
});

// ===== TEXTS FOR THE SERVER CONFIG =====
test("every game category, event and level in game/scenarios.py has an English text", () => {
  const en = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "frontend", "lang", "en.json"), "utf8"));
  const config = fs.readFileSync(path.join(__dirname, "..", "..", "backend", "game", "scenarios.py"), "utf8");
  for (const [, id] of config.matchAll(/\{"id": "([a-z_]+)", "kind"/g)) assert.ok("game.cat." + id in en, id);
  for (const [, id] of config.matchAll(/\{"id": "([a-z_]+)", "type"/g)) assert.ok("game.event." + id in en, id);
  for (const [, n] of config.matchAll(/"level": (\d+)/g)) {
    assert.ok("game.levelTitle." + n in en && "game.levelStory." + n in en, "level " + n);
  }
  for (const key of ["balance", "essentials", "allocation", "savings", "events"]) assert.ok("game.crit." + key in en);
  for (const code of ["balanced", "overspend", "essential_short", "save_vs_essentials", "high_needs_ok", "needs_high", "large_wants",
    "no_savings", "savings_low", "unassigned", "event_handled", "event_failed", "great"])
    assert.ok("game.tip." + code in en, code);
});
