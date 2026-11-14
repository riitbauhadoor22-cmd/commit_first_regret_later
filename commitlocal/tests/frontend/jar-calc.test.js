// jar-calc.test.js — tests for frontend/jar-calc.js (the savings jar: liquid level, wave, coins, when to animate).
// Run: node --test tests/frontend/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const J = require("../../frontend/jar-calc.js");

test("the liquid level follows the saved percent exactly", () => {
  assert.equal(J.levelY(0), J.BOTTOM_Y);
  assert.equal(J.levelY(100), J.TOP_Y);
  assert.equal(J.levelY(50), (J.BOTTOM_Y + J.TOP_Y) / 2);
  assert.ok(J.levelY(40) > J.levelY(60)); // more saved = higher surface (smaller y)
  assert.equal(J.fillShare(40), 0.4);
});

test("bad or out-of-range percents never give NaN or an overfull jar", () => {
  for (const value of [undefined, null, "", "abc", NaN, -5]) {
    assert.equal(J.levelY(value), J.BOTTOM_Y);
    assert.equal(J.coinCount(value), 0);
  }
  assert.equal(J.levelY(250), J.TOP_Y);
  assert.equal(J.fillShare(250), 1);
});

test("the wave path is valid, covers twice the jar width (for the loop) and stays subtle", () => {
  const path = J.wavePath();
  assert.ok(path.startsWith("M0 0") && path.endsWith("V260 H0 Z"));
  assert.ok(path.includes(" 400 0"), "reaches x = 400");
  assert.ok(!path.includes("NaN"));
  const heights = [...path.matchAll(/Q[\d.]+ (-?[\d.]+)/g)].map((m) => Math.abs(Number(m[1])));
  assert.ok(heights.length > 0 && heights.every((h) => h <= 5), "wave is at most 5 units high");
});

test("a few decoration coins: none at 0%, one as soon as anything is saved, at most 6", () => {
  assert.equal(J.coinCount(0), 0);
  assert.equal(J.coinCount(0.1), 1);
  assert.equal(J.coinCount(40), 3);
  assert.equal(J.coinCount(100), J.MAX_COINS);
  for (const coin of J.layoutCoins(100)) {
    assert.ok(coin.x >= 40 && coin.x <= 160, "inside the jar walls");
    assert.ok(coin.y <= J.BOTTOM_Y && coin.y >= J.TOP_Y, "inside the jar");
  }
});

test("positions are the same every time (no random jumping)", () => {
  assert.deepEqual(J.layoutCoins(65), J.layoutCoins(65));
  assert.equal(J.wavePath(), J.wavePath());
});

test("animate only when the saved amount went up since last time", () => {
  assert.equal(J.shouldAnimate(null, 500), false);      // first time on this phone: no animation
  assert.equal(J.shouldAnimate(undefined, 500), false);
  assert.equal(J.shouldAnimate(300, 500), true);         // money added: rise + one coin
  assert.equal(J.shouldAnimate(500, 500), false);        // nothing changed
  assert.equal(J.shouldAnimate(800, 500), false);        // less money: just the new level
  assert.equal(J.shouldAnimate("abc", 500), false);
});
