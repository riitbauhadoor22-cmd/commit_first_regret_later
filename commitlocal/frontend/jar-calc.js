// jar-calc.js — the maths for the Dashboard's savings jar (a glass jar with liquid + a few coins). No screen code here,
// so the same file runs in the browser and in Node tests (tests/frontend/jar-calc.test.js).
// The jar is an SVG (viewBox 0 0 200 240). The liquid fills from the bottom up to saved ÷ target × 100 %, with a
// gentle wave on top. A few coins sit in the liquid as decoration. Everything is DETERMINISTIC (no Math.random),
// so the jar looks the same every time for the same numbers.
(function () {
  const BOTTOM_Y = 222;      // inside bottom of the jar (0% = liquid surface here)
  const TOP_Y = 64;          // just under the jar's shoulder (100% = liquid surface here)
  const WAVE_LENGTH = 50;    // one wave on the surface, in SVG units
  const WAVE_HEIGHT = 3.5;   // how high the wave goes up and down (subtle)
  const MAX_COINS = 6;       // decoration coins at the bottom of the jar
  // Where the decoration coins rest (bottom row first), and their tilt in degrees
  const COIN_SPOTS = [
    { x: 72, y: 212, rotate: -8 }, { x: 102, y: 214, rotate: 6 }, { x: 132, y: 212, rotate: -4 },
    { x: 87, y: 203, rotate: 10 }, { x: 117, y: 203, rotate: -12 }, { x: 102, y: 194, rotate: 4 },
  ];

  // Percent saved (anything) → 0..100 (never NaN)
  function clampPercent(percent) {
    const number = Number(percent);
    if (!Number.isFinite(number) || number <= 0) return 0;
    return Math.min(number, 100);
  }

  // Share of the jar that is full (0..1)
  function fillShare(percent) {
    return clampPercent(percent) / 100;
  }

  // The y of the liquid surface: 0% → BOTTOM_Y, 100% → TOP_Y (smaller y = higher in the SVG)
  function levelY(percent) {
    return Math.round((BOTTOM_Y - (BOTTOM_Y - TOP_Y) * fillShare(percent)) * 10) / 10;
  }

  // The liquid shape drawn at y = 0: a wavy top from x = 0 to 400 (twice the jar's width, so it can slide
  // sideways in a loop), then straight down past the jar's bottom. The page moves it down to levelY().
  function wavePath() {
    let path = "M0 0";
    for (let x = 0; x < 400; x += WAVE_LENGTH) {
      path += " Q" + (x + WAVE_LENGTH / 4) + " " + -WAVE_HEIGHT + " " + (x + WAVE_LENGTH / 2) + " 0";
      path += " Q" + (x + (WAVE_LENGTH * 3) / 4) + " " + WAVE_HEIGHT + " " + (x + WAVE_LENGTH) + " 0";
    }
    return path + " V260 H0 Z";
  }

  // How many decoration coins: none at 0%, 1 as soon as anything is saved, then one more every 20% (max 6)
  function coinCount(percent) {
    const p = clampPercent(percent);
    if (p === 0) return 0;
    return Math.min(MAX_COINS, 1 + Math.floor(p / 20));
  }

  // The coins for a percent, bottom first; the last one is the one that drops in when money was added
  function layoutCoins(percent) {
    return COIN_SPOTS.slice(0, coinCount(percent)).map((spot, index) => ({ ...spot, index: index }));
  }

  // Animate only when the saved amount went UP since this phone last showed the jar (null = never shown: no animation)
  function shouldAnimate(previousSaved, saved) {
    if (previousSaved === null || previousSaved === undefined || !Number.isFinite(Number(previousSaved))) return false;
    return Number(saved) > Number(previousSaved);
  }

  const JarCalc = { BOTTOM_Y, TOP_Y, WAVE_LENGTH, WAVE_HEIGHT, MAX_COINS, clampPercent, fillShare, levelY, wavePath,
    coinCount, layoutCoins, shouldAnimate };
  if (typeof window !== "undefined") window.JarCalc = JarCalc; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = JarCalc; // Node tests
})();
