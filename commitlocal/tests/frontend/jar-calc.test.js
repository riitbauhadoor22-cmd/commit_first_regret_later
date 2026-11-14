// jar-calc.test.js — tests for frontend/jar-calc.js (the savings jar's coins). Run: node --test tests/frontend/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const J = require("../../frontend/jar-calc.js");

test("the number of coins follows the saved percent", () => {
  assert.equal(J.coinCount(0), 0);
  assert.equal(J.coinCount(20), Math.round(0.2 * J.MAX_COINS));
  assert.equal(J.coinCount(40), Math.round(0.4 * J.MAX_COINS));
  assert.equal(J.coinCount(100), J.MAX_COINS);
  assert.equal(J.coinCount(0.1), 1); // anything saved shows at least one coin
});

test("bad or out-of-range percents never give NaN or an overfull jar", () => {
  for (const value of [undefined, null, "", "abc", NaN, -5]) assert.equal(J.coinCount(value), 0);
  assert.equal(J.coinCount(250), J.MAX_COINS);
  assert.equal(J.fillShare(250), 1);
  assert.equal(J.fillShare(40), 0.4);
});

test("coins stack from the bottom up and the pile height matches the percent", () => {
  const coins = J.layoutCoins(40);
  const highestRow = Math.floor((coins.length - 1) / J.PER_ROW);
  assert.equal(highestRow + 1, Math.ceil((0.4 * J.MAX_COINS) / J.PER_ROW)); // 2/5 of the rows
  assert.ok(coins[0].y > coins[coins.length - 1].y); // first coin lowest (bigger y = lower in SVG)
  for (const coin of coins) {
    assert.ok(coin.x >= 45 && coin.x <= 155, "inside the jar walls");
    assert.ok(coin.y >= J.TOP_Y - 3 && coin.y <= J.BOTTOM_Y + 3, "inside the jar height");
    assert.ok(Math.abs(coin.rotate) <= 14);
  }
});

test("positions are the same every time (no random jumping)", () => {
  assert.deepEqual(J.layoutCoins(65), J.layoutCoins(65));
  assert.deepEqual(J.coinPosition(7), J.coinPosition(7));
});

test("only coins above the old count are new (they drop in)", () => {
  const coins = J.layoutCoins(50, J.coinCount(30));
  const fresh = coins.filter((coin) => coin.isNew);
  assert.equal(fresh.length, J.coinCount(50) - J.coinCount(30));
  assert.ok(fresh.every((coin) => coin.index >= J.coinCount(30)));
  assert.equal(J.layoutCoins(50).filter((coin) => coin.isNew).length, 0); // no old count = no animation
});
