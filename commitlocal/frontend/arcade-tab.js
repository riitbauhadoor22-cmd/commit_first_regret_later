// arcade-tab.js — the "Budget Challenge" game (on the Profile tab, it used to be the Arcade tab): pick a level, split a fictional income between the
// level's own categories, see ONE surprise event, adjust once, then get a score out of 100, tips and XP.
// The server (/api/game) picks the event, works out the score and gives XP once per game. Texts: "game.*" keys.
// Uses formatMoney / makeElement / makeLegendItem from app.js and money-tab.js, and GameCalc from game-calc.js.

// ===== STATE =====
const gameState = {
  levels: [],        // level configs from GET /api/game/levels
  bestScores: {},    // {"1": 90, ...}
  attempt: null,     // {attempt_id, level, has_event} of the game being played
  event: null,       // the surprise event once revealed
  values: {},        // what the player typed {category id: text}
  result: null,      // last final result (for redrawing after a language switch)
  busy: false,
};

// ===== SMALL HELPERS =====
function gameCategoryName(id) { return t("game.cat." + id) || id; }
function gameMoney(amount) { return formatMoney(GameCalc.toAmount(amount)); } // never "Rs NaN"

// The income for this game: base income + a bonus event (once revealed)
function gameIncome() {
  const level = gameState.attempt.level;
  const bonus = gameState.event && gameState.event.type === "bonus" ? gameState.event.amount : 0;
  return level.income + bonus;
}

// Minimum for a category: locked amount or min_amount, + a cost / − a discount event on it (once revealed)
function gameMinimum(category) {
  const base = category.locked !== undefined ? category.locked : category.min_amount || 0;
  const event = gameState.event;
  if (!event || event.category !== category.id || event.type === "bonus") return base;
  return Math.max(0, base + (event.type === "cost" ? event.amount : -event.amount));
}

// ===== API CALLS =====
async function loadArcadeTab() {
  if (gameState.attempt) return; // a game is in progress: keep it as it is
  try {
    const [levels, history] = await Promise.all([getGameLevels(), getGameAttempts()]);
    gameState.levels = levels.levels;
    drawGameHistory(history);
    drawLevelButtons();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function startGame(levelNumber) {
  if (gameState.busy) return;
  gameState.busy = true;
  try {
    const attempt = await startGameAttempt(levelNumber, byId("game-events").checked);
    Object.assign(gameState, { attempt: attempt, event: null, result: null, values: {} });
    attempt.level.categories.forEach((category) => {
      gameState.values[category.id] = category.locked !== undefined ? String(category.locked) : "";
    });
    showGameSection("game-play");
    drawGamePlay();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    gameState.busy = false;
  }
}

async function submitGame(event) {
  event.preventDefault();
  if (gameState.busy || !gameState.attempt) return;
  const categories = gameState.attempt.level.categories;
  if (categories.some((c) => GameCalc.isBadAmount(gameState.values[c.id]))) {
    showFormError("game-error", t("game.badAmount"));
    return;
  }
  const allocation = {};
  categories.forEach((c) => { allocation[c.id] = GameCalc.toAmount(gameState.values[c.id]); });
  // With an event: the first submit only reveals it; the next one is final. Without: straight to the result.
  const isFinal = !gameState.attempt.has_event || gameState.event !== null;
  gameState.busy = true;
  byId("game-error").textContent = "";
  try {
    const reply = await submitGameAttempt(gameState.attempt.attempt_id, allocation, isFinal);
    if (reply.stage === "event") {
      gameState.event = reply.event;
      drawGamePlay();
      byId("game-event").scrollIntoView({ block: "center", behavior: "smooth" });
    } else {
      gameState.result = reply;
      showGameSection("game-result");
      drawGameResult(true);
      getGameAttempts().then(drawGameHistory).catch(() => {}); // refresh previous results + XP quietly
    }
  } catch (error) {
    showFormError("game-error", error.message);
  } finally {
    gameState.busy = false;
  }
}

// ===== UI: LEVEL PICKER + HISTORY =====
function showGameSection(id) {
  byId("game-card").hidden = id !== "game-card";
  byId("game-play").hidden = id !== "game-play";
  byId("game-result").hidden = id !== "game-result";
  window.scrollTo(0, 0);
}

function drawLevelButtons() {
  const box = byId("game-levels");
  box.replaceChildren(...gameState.levels.map((level) => {
    const button = makeElement("button", "btn btn-light game-level-btn");
    button.type = "button";
    const best = gameState.bestScores[String(level.level)];
    button.append(
      makeElement("span", "game-level-name", t("game.levelN", { n: level.level }) + " · " + t("game.levelTitle." + level.level)),
      makeElement("span", "game-level-sub", t("game.incomeShort", { amount: gameMoney(level.income) }) +
        (best !== undefined ? " · " + t("game.best", { n: best }) : ""))
    );
    button.addEventListener("click", () => startGame(level.level));
    return button;
  }));
}

function drawGameHistory(history) {
  gameState.bestScores = history.best_scores || {};
  setText(byId("game-xp"), "game.totalXp", { n: history.total_xp || 0 });
  const list = byId("game-history");
  const attempts = history.attempts || [];
  if (attempts.length === 0) {
    list.replaceChildren(makeElement("li", "empty", t("game.noResults")));
    return;
  }
  list.replaceChildren(...attempts.map((attempt) => {
    const item = makeElement("li", "item");
    const left = makeElement("div");
    const when = GameCalc.parseUtc(attempt.completed_at); // UTC from the server -> this phone's local date
    const date = when ? I18n.formatDate(when, { day: "numeric", month: "short" }) : "";
    left.append(makeElement("span", "item-name", t("game.levelN", { n: attempt.level }) + " · " +
                            t("game.levelTitle." + attempt.level)),
                makeElement("span", "item-sub", date));
    const right = makeElement("span", "item-amount", (attempt.score || 0) + "/100 · " + t("game.xpPlus", { n: attempt.xp || 0 }));
    item.append(left, right);
    return item;
  }));
}

// ===== UI: PLAYING =====
function drawGamePlay() {
  const level = gameState.attempt.level;
  byId("game-level-title").textContent = t("game.levelN", { n: level.level }) + " · " + t("game.levelTitle." + level.level);
  byId("game-story").textContent = t("game.levelStory." + level.level);
  byId("game-income").textContent = t("game.income", { amount: gameMoney(gameIncome()) });
  drawGameEvent();
  setText(byId("game-submit"), gameState.event ? "game.submitFinal" : "game.submit");

  const box = byId("game-fields");
  box.replaceChildren(...level.categories.map(makeGameField));
  updateGameTotals();
}

function drawGameEvent() {
  const box = byId("game-event");
  const event = gameState.event;
  box.hidden = !event;
  if (!event) return;
  const params = { amount: gameMoney(event.amount), category: gameCategoryName(event.category) };
  const effect = t(event.type === "bonus" ? "game.eventBonus" : event.type === "discount" ? "game.eventDiscount" : "game.eventCost", params);
  box.replaceChildren(
    makeElement("p", "game-event-title", t("game.eventTitle")),
    makeElement("p", "", t("game.event." + event.id, { amount: gameMoney(event.amount) })),
    makeElement("p", "muted", effect + " " + t("game.adjustOnce"))
  );
}

function makeGameField(category) {
  const locked = category.locked !== undefined;
  const label = makeElement("label", "game-field");
  const top = makeElement("span", "game-field-top");
  top.append(makeElement("span", "", (locked ? "🔒 " : "") + gameCategoryName(category.id)),
             makeElement("span", "tag game-kind-" + category.kind, t("game.kind." + category.kind)));
  const input = makeElement("input");
  Object.assign(input, { type: "number", inputMode: "decimal", min: "0", step: "any", placeholder: "0",
                         value: gameState.values[category.id] || "" });
  input.disabled = locked; // fixed commitments can't be changed
  input.addEventListener("input", () => {
    gameState.values[category.id] = input.value;
    updateGameTotals();
  });
  label.append(top, input);
  const minimum = gameMinimum(category);
  if (locked) label.append(makeElement("span", "muted", t("game.locked")));
  else if (minimum > 0) label.append(makeElement("span", "muted", t("game.suggested", { amount: gameMoney(minimum) })));
  return label;
}

// Live total, money left and the Needs / Wants / Savings bar while typing (display only)
function updateGameTotals() {
  const totals = GameCalc.allocationTotals(gameState.attempt.level.categories, gameState.values, gameIncome());
  drawGameBar("game-split-", totals);
  byId("game-split-legend").replaceChildren(...gameLegend(totals), makeElement("span", "aim", t("money.aim")));
  byId("game-allocated").textContent = t("game.allocated", { amount: gameMoney(totals.total) });
  const left = byId("game-left");
  const isOver = totals.left < 0;
  left.classList.toggle("over", isOver);
  left.textContent = isOver
    ? t("game.over", { amount: gameMoney(-totals.left) })
    : t("game.left", { amount: gameMoney(totals.left) });
  byId("game-submit").disabled = isOver; // over income can't be submitted (the server blocks it too)
}

function drawGameBar(prefix, totals) {
  const widths = GameCalc.barWidths(totals.needs, totals.wants, totals.savings);
  byId(prefix + "needs").style.width = widths.needs + "%";
  byId(prefix + "wants").style.width = widths.wants + "%";
  byId(prefix + "savings").style.width = widths.savings + "%";
}

// "Needs 50% · Rs 7,500" etc. (amounts optional). Same colours as the Money tab bar.
function gameLegend(totals) {
  const amounts = totals.amounts || {};
  const item = (colour, key, percent, amount) => makeLegendItem(colour, t(key, { n: Math.round(percent || 0) }) + // in money-tab.js
    (amount !== undefined ? " · " + gameMoney(amount) : ""));
  return [
    item("split-needs", "game.group.need", totals.needs, amounts.need),
    item("split-wants", "game.group.want", totals.wants, amounts.want),
    item("split-savings", "game.group.savings", totals.savings, amounts.savings),
  ];
}

// ===== UI: RESULT =====
function drawGameResult(animate) {
  const result = gameState.result;
  animateGameScore(result.score || 0, animate);

  let xpText = t("game.xpAlready");
  if (result.xp_awarded > 0) {
    xpText = t("game.xpWon", { n: result.xp_awarded }) + (result.first_completion_bonus ? " " + t("game.xpBonus") : "");
  }
  byId("game-xp-won").textContent = xpText;

  byId("game-breakdown").replaceChildren(...result.breakdown.map((part) => {
    const item = makeElement("li", "game-part");
    const top = makeElement("div", "cat-top");
    const points = part.points === null ? "–" : part.points; // never "null" / "NaN"
    top.append(makeElement("span", "cat-name", t("game.crit." + part.key)), makeElement("span", "cat-amount", points + " / " + part.max));
    const bar = makeElement("div", "bar");
    const fill = makeElement("span", "game-part-fill");
    bar.append(fill);
    item.append(top, bar);
    const width = part.max > 0 ? (Number(part.points) || 0) / part.max * 100 : 0;
    requestAnimationFrame(() => { fill.style.width = width + "%"; }); // CSS transition grows the bar
    return item;
  }));

  // Your split vs the 50 · 30 · 20 goal (same colours as the Money tab bar)
  const percents = result.percents || {};
  const yours = { needs: percents.need || 0, wants: percents.want || 0, savings: percents.savings || 0, amounts: result.totals };
  byId("game-summary").replaceChildren(
    makeElement("li", "", t("game.income", { amount: gameMoney(result.income) })),
    makeElement("li", "", t("game.allocated", { amount: gameMoney(result.total) })),
    makeElement("li", result.left < 0 ? "over" : "", result.left < 0
      ? t("game.over", { amount: gameMoney(-result.left) }) : t("game.left", { amount: gameMoney(result.left) })));
  fillSplitBar(byId("game-result-bar"), yours);
  fillSplitBar(byId("game-goal-bar"), { needs: 50, wants: 30, savings: 20 });
  byId("game-result-legend").replaceChildren(...gameLegend(yours), makeElement("span", "aim", t("money.aim")));

  byId("game-tips").replaceChildren(...result.tips.map((tip) => makeElement("li", "", gameTipText(tip))));
}

function fillSplitBar(bar, totals) {
  const widths = GameCalc.barWidths(totals.needs, totals.wants, totals.savings);
  bar.replaceChildren(...["needs", "wants", "savings"].map((kind) => {
    const span = makeElement("span", "split-" + kind);
    span.style.width = widths[kind] + "%";
    return span;
  }));
}

// Tip codes from the server -> text. Money and category ids are formatted / translated here.
function gameTipText(tip) {
  const params = Object.assign({}, tip.params);
  ["over", "min", "target", "left", "amount"].forEach((key) => {
    if (key in params) params[key] = gameMoney(params[key]);
  });
  if (params.category) params.category = gameCategoryName(params.category);
  return t("game.tip." + tip.code, params);
}

// Count the score up from 0 (skipped when the phone asks for less motion)
function animateGameScore(score, animate) {
  const element = byId("game-score");
  const still = !animate || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  if (still) {
    element.textContent = score + " / 100";
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const share = Math.min(1, (now - start) / 700);
    element.textContent = Math.round(score * share) + " / 100";
    if (share < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ===== UI: BUTTONS + LANGUAGE SWITCH =====
function leaveGame() {
  Object.assign(gameState, { attempt: null, event: null, result: null, values: {} });
  showGameSection("game-card");
  loadArcadeTab();
}

function playAgain() {
  const level = gameState.attempt ? gameState.attempt.level.level : 1;
  startGame(level);
}

function redrawArcade() {
  if (!byId("game-play").hidden && gameState.attempt) drawGamePlay();
  if (!byId("game-result").hidden && gameState.result) drawGameResult(false);
  if (gameState.levels.length > 0) drawLevelButtons();
  getGameAttempts().then(drawGameHistory).catch(() => {});
}

function setUpArcade() {
  byId("game-form").addEventListener("submit", submitGame);
  byId("game-quit").addEventListener("click", leaveGame);
  byId("game-back").addEventListener("click", leaveGame);
  byId("game-again").addEventListener("click", playAgain);
}

setUpArcade();
