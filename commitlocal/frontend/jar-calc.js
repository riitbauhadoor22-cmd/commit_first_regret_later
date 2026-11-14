// jar-calc.js — where the coins go in the Dashboard's savings jar. No screen code here, so the same file runs in the
// browser and in Node tests (tests/frontend/jar-calc.test.js).
// The jar is an SVG (viewBox 0 0 200 240). Coins are stacked in rows from the bottom up; the number of coins (and so
// the height of the pile) follows the saved percentage exactly: 40% saved = 40% of the coins = 2/5 of the jar.
// Positions are DETERMINISTIC (a small hash of the coin number, never Math.random), so the pile never jumps around.
(function () {
  const ROWS = 18;            // rows of coins when the jar is full
  const PER_ROW = 5;          // coins side by side in one row
  const MAX_COINS = ROWS * PER_ROW; // 90 coins = 100% (the number of coins is capped, the fill level stays exact)
  const BOTTOM_Y = 212;       // centre of the lowest row (inside the jar's base)
  const TOP_Y = 62;           // centre of the highest row (just under the neck)
  const LEFT_X = 50;          // centre of the first coin in a row
  const RIGHT_X = 150;        // centre of the last coin in a row
  const ROW_GAP = (BOTTOM_Y - TOP_Y) / (ROWS - 1);

  // Percent saved (anything) → 0..100
  function clampPercent(percent) {
    const number = Number(percent);
    if (!Number.isFinite(number) || number <= 0) return 0;
    return Math.min(number, 100);
  }

  // How many coins to draw: 0% → 0, 100% → MAX_COINS, and at least 1 coin as soon as anything is saved
  function coinCount(percent) {
    const p = clampPercent(percent);
    if (p === 0) return 0;
    return Math.max(1, Math.round((p / 100) * MAX_COINS));
  }

  // A fixed "random-looking" number between -1 and 1 for coin n (same n → same number, every time)
  function wobble(n, salt) {
    const x = Math.sin(n * 12.9898 + salt * 78.233) * 43758.5453;
    return (x - Math.floor(x)) * 2 - 1;
  }

  // Position of coin number `index` (0 = bottom left): x, y in the SVG and a small tilt in degrees
  // Even rows go edge to edge; odd rows are a bit narrower and shifted, so coins sit in the gaps like a real pile.
  function coinPosition(index) {
    const row = Math.floor(index / PER_ROW);
    const column = index % PER_ROW;
    const step = (RIGHT_X - LEFT_X) / (PER_ROW - 1);
    const x = row % 2 === 0
      ? LEFT_X + column * step
      : LEFT_X + step / 2 + column * (step * (PER_ROW - 2)) / (PER_ROW - 1);
    return {
      x: Math.round((x + wobble(index, 1) * 3) * 10) / 10,
      y: Math.round((BOTTOM_Y - row * ROW_GAP + wobble(index, 2) * 1.5) * 10) / 10,
      rotate: Math.round(wobble(index, 3) * 14),
    };
  }

  // All coins for a percent, bottom first. Coins with index >= fromCount are "new" (they drop in).
  function layoutCoins(percent, fromCount) {
    const count = coinCount(percent);
    const coins = [];
    for (let i = 0; i < count; i++) {
      coins.push({ ...coinPosition(i), index: i, isNew: fromCount !== undefined && i >= fromCount });
    }
    return coins;
  }

  // Height of the pile as a share of the jar (0..1): matches the percent
  function fillShare(percent) {
    return clampPercent(percent) / 100;
  }

  const JarCalc = { ROWS, PER_ROW, MAX_COINS, TOP_Y, BOTTOM_Y, clampPercent, coinCount, coinPosition, layoutCoins, fillShare };
  if (typeof window !== "undefined") window.JarCalc = JarCalc; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = JarCalc; // Node tests
})();
