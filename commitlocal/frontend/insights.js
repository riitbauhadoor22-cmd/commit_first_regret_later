// insights.js — the "Financial insights" card at the bottom of the Money tab.
// Opening the tab only READS what's saved (GET /api/insights): the 50/30/20 check-up (plain maths, no AI)
// and the last AI analysis. The AI (Groq, on our server) is only asked when the user taps the button,
// and the server decides whether a new analysis is really needed. The button is disabled while it runs.
// When the AI isn't set up, is blocked or fails, the button gives "Quick insights (no AI)" instead
// (POST /api/insights/quick: plain maths from the user's own numbers). The button is never left dead.
// Uses STATUS_KEYS / STATUS_CLASSES from savings-view.js (loaded before this file).

// ===== STATE =====
let insightsData = null;   // last reply from the server
let insightsMonth = null;  // month the card is showing
let insightsBusy = false;  // true while a "Generate" request runs
let insightsMode = "ai";   // what the main button does: "ai" (ask Groq) or "quick" (no AI)
const AI_CLIENT_TIMEOUT_MS = 45000; // the server gives up after AI_TIMEOUT_SECONDS; this only covers a stuck network

const GROUP_KEYS = { needs: "insights.group.needs", wants: "insights.group.wants", savings_and_debt: "insights.group.savings" };
const PRIORITY_TEXT_KEYS = { high: "insights.priority.high", medium: "insights.priority.medium", low: "insights.priority.low" };

// ===== LOAD (no AI call) =====
async function loadInsights(month) {
  insightsMonth = month;
  try {
    drawInsights(await getInsights(month));
  } catch (error) {
    byId("insights-status").textContent = error.message;
  }
}

function drawInsights(data) {
  insightsData = data;
  drawSplitTable(data.analysis.split);
  drawEmptyActions(data.analysis);
  drawCheckupNotes(data.analysis);
  drawInsightGoals(data.analysis.goals);
  drawAiAnalysis(data.saved);
  byId("insights-quick").hidden = true; // new numbers: an old quick list would be out of date
  drawInsightsButton();
}

// ===== 50/30/20 TABLE =====
function drawSplitTable(rows) {
  const box = byId("insights-split");
  box.replaceChildren();
  rows.forEach((row) => {
    const line = makeElement("div", "split-row");
    const left = makeElement("div");
    left.append(makeElement("span", "item-name", t(GROUP_KEYS[row.group])),
      makeElement("span", "item-sub", row.amount === null ? "—" : formatMoney(Math.round(row.amount))));
    const right = makeElement("div", "split-numbers");
    const actual = row.percent === null ? "—" : Math.round(row.percent) + "%";
    right.append(makeElement("span", "item-name", t("insights.actualVsAim", { actual: actual, aim: row.target_percent })),
      makeElement("span", "item-sub", describeDifference(row)));
    line.append(left, right);
    box.append(line);
  });
}

// Not given → "no expenses / savings recorded yet"; no income → "add income to compare"; loans unknown → "loans not included"
function describeDifference(row) {
  const points = row.difference_points;
  if (row.amount === null) return t(row.group === "savings_and_debt" ? "insights.noSavingsShort" : "insights.noExpensesShort");
  if (row.percent === null) return t("insights.noIncomeShort");
  if (points === null) return t("insights.loansUnknown");
  const rounded = Math.round(points);
  if (rounded === 0) return t("insights.onAim");
  return t(rounded > 0 ? "insights.pointsAbove" : "insights.pointsBelow", { n: Math.abs(rounded) });
}

// ===== EMPTY STATES: buttons to the right place (Money in / Money out / Savings) =====
function makeLinkButton(key, onClick) {
  const button = makeElement("button", "link-btn", t(key));
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

function openMoneyForm(view, openSheet) {
  showMoneyView(view); // money-tab.js: Money in / Money out
  openSheet();
}

function drawEmptyActions(analysis) {
  const box = byId("insights-empty-actions");
  box.replaceChildren();
  if (!analysis.take_home_income) { // missing or 0: percents can't be compared
    box.append(makeLinkButton("insights.addIncome", () => openMoneyForm("in", () => openIncomeSheet(null, "monthly"))));
  }
  if (analysis.needs === null) {
    box.append(makeLinkButton("insights.addExpense", () => openMoneyForm("out", () => openExpenseSheet(null))));
  }
  if (analysis.savings === null) {
    box.append(makeLinkButton("insights.addSavings", () => openSavingsView()));
  }
  box.hidden = box.childElementCount === 0;
}

// ===== PLAIN-MATHS NOTES + WHAT WE DON'T KNOW =====
function drawCheckupNotes(analysis) {
  const list = byId("insights-notes");
  list.replaceChildren();
  analysis.observations.forEach((note) => {
    const params = Object.assign({}, note.params);
    if (typeof params.amount === "number") params.amount = formatMoney(params.amount);
    list.append(makeElement("li", "", t("insights.obs." + note.code, params)));
  });
  // What the user hasn't given yet, as friendly prompts (never as Rs 0)
  byId("insights-gaps").textContent = analysis.data_gaps.map((code) => t("insights.gap." + code)).join(" ");
}

// ===== GOAL PROGRESS =====
function drawInsightGoals(goals) {
  const list = byId("insights-goals");
  list.replaceChildren();
  byId("insights-goals-title").hidden = goals.length === 0;
  goals.forEach((goal) => {
    const li = makeElement("li", "insight-goal");
    const top = makeElement("div", "card-head");
    top.append(makeElement("span", "item-name", goal.name),
      makeElement("span", "status " + STATUS_CLASSES[goal.status], t(STATUS_KEYS[goal.status]) || goal.status));
    const bar = makeElement("div", "meter");
    const fill = makeElement("div", "meter-fill");
    fill.style.width = Math.min(goal.percent, 100) + "%";
    bar.append(fill);
    li.append(top, bar, makeElement("span", "item-sub", describeGoalPlan(goal)));
    if (goal.status !== "Done" && goal.plan !== "ok") { // no monthly amount without a target + a date still ahead
      li.append(makeLinkButton("insights.editGoal", () => editGoalFromInsights(goal.id)));
    }
    list.append(li);
  });
}

// "40% saved · needs Rs 2,000 a month" only when the goal has a target and a date still ahead
function describeGoalPlan(goal) {
  const percent = Math.round(goal.percent || 0);
  if (goal.status === "Done") return t("insights.goalDoneLine", { percent: percent });
  if (goal.plan === "deadline_passed") return t("goal.deadlinePassed");
  if (goal.plan !== "ok" || goal.needs_per_month === null) return t("goal.noPlan");
  return t("insights.goalLine", { percent: percent, amount: formatMoney(Math.round(goal.needs_per_month)) });
}

// Money → Savings at that goal, with its edit form open
async function editGoalFromInsights(goalId) {
  await openSavingsView(goalId); // money-tab.js
  const goal = goalsInfo && goalsInfo.goals.find((item) => item.id === goalId); // savings-view.js
  if (goal) openGoalSheet(goal);
}

// ===== SAVED AI ANALYSIS =====
function drawAiAnalysis(saved) {
  const box = byId("insights-ai");
  box.replaceChildren();
  const date = byId("insights-date");
  if (!saved.insight) {
    date.textContent = "";
    box.append(makeElement("p", "muted", t(insightsData.ai_configured ? "insights.empty" : "insights.emptyNoAi")));
    return;
  }
  date.textContent = t("insights.generatedOn", {
    date: I18n.formatDate(new Date(saved.generated_at), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) });
  if (saved.status === "outdated") box.append(makeElement("p", "tip", t("insights.outdated")));

  const ai = saved.insight;
  box.append(makeElement("p", "", ai.overview));
  if (ai.observations.length) {
    const list = makeElement("ul", "insight-notes");
    ai.observations.forEach((text) => list.append(makeElement("li", "", text)));
    box.append(list);
  }
  ai.suggestions.forEach((tip) => box.append(makeSuggestionCard(tip)));
  if (ai.savings_analysis) box.append(makeElement("p", "", ai.savings_analysis));
  if (ai.encouragement) box.append(makeElement("p", "insight-cheer", ai.encouragement));
}

function makeSuggestionCard(tip) {
  const card = makeElement("div", "suggestion");
  const top = makeElement("div", "card-head");
  top.append(makeElement("span", "item-name", tip.title),
    makeElement("span", "tag priority-" + tip.priority, t(PRIORITY_TEXT_KEYS[tip.priority])));
  card.append(top, makeElement("p", "", tip.description),
    makeElement("p", "item-sub", t("insights.why", { reason: tip.reason })));
  return card;
}

// ===== QUICK INSIGHTS (no AI) =====
function describeQuickTip(tip) {
  const params = Object.assign({}, tip.params);
  if (typeof params.amount === "number") params.amount = formatMoney(Math.round(params.amount));
  if (params.group) params.group = t(GROUP_KEYS[params.group]);
  if (params.category) params.category = tCategory(params.category);
  return t("insights.quick." + tip.code, params);
}

async function showQuickInsights() {
  const box = byId("insights-quick");
  const title = () => makeElement("p", "small-title", t("insights.quickTitle"));
  box.hidden = false;
  box.replaceChildren(title(), makeElement("p", "muted", t("insights.quickLoading")));
  try {
    const data = await getQuickInsights(insightsMonth);
    const list = makeElement("ul", "insight-notes");
    data.quick.forEach((tip) => list.append(makeElement("li", "", describeQuickTip(tip))));
    box.replaceChildren(title(), list);
  } catch (error) {
    box.replaceChildren(title(), makeElement("p", "muted", error.message));
  }
}

// ===== THE BUTTON (the only thing that can make the server call Groq) =====
function drawInsightsButton() {
  const button = byId("insights-btn");
  const status = byId("insights-status");
  const data = insightsData;
  if (insightsBusy) {
    button.disabled = true;
    setText(button, "insights.working");
    return;
  }
  button.disabled = false;
  status.textContent = "";
  let blocked = "";
  if (!data.analysis.enough_for_ai) blocked = t("error.AI_NOT_ENOUGH_DATA"); // nothing given yet: nothing to explain
  else if (!data.ai_configured) blocked = t("insights.notConfigured");
  else if (data.usage.used_today >= data.usage.daily_limit) blocked = t("error.AI_DAILY_LIMIT", { limit: data.usage.daily_limit });
  else if (data.paused_seconds > 0) blocked = t("error.AI_RATE_LIMITED", { seconds: data.paused_seconds });
  if (data.saved.status === "fresh") {
    insightsMode = "ai";
    setText(button, "insights.upToDate"); // same data as last time: asking again would give the same answer
    button.disabled = true;
    return;
  }
  // AI can't run now → the same button gives quick insights from the user's numbers (never a dead button)
  insightsMode = blocked ? "quick" : "ai";
  setText(button, blocked ? "insights.quickButton" : data.saved.status === "outdated" ? "insights.refresh" : "insights.generate");
  status.textContent = blocked;
}

// Rejects with the friendly timeout text if the request hangs (e.g. a stuck mobile network)
function withTimeout(promise) {
  let timer;
  const timeout = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(t("error.AI_TIMEOUT"))), AI_CLIENT_TIMEOUT_MS);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function onInsightsButton() {
  if (insightsMode === "quick") return showQuickInsights();
  return generateInsightsNow();
}

async function generateInsightsNow() {
  if (insightsBusy || !insightsData) return; // a double tap does nothing
  insightsBusy = true;
  byId("insights-quick-btn").hidden = true;
  drawInsightsButton();
  let problem = "";
  try {
    const data = await withTimeout(generateInsights(insightsMonth));
    insightsBusy = false;
    drawInsights(data);
  } catch (error) {
    problem = error.message; // the maths and the last analysis stay on screen
  } finally {
    insightsBusy = false;
  }
  if (problem) {
    drawInsightsButton();
    byId("insights-status").textContent = problem + " " + t("insights.tryQuick");
    byId("insights-quick-btn").hidden = false; // offer the no-AI version
  }
}

// ===== START (called by money-tab.js) =====
function startInsights() {
  byId("insights-btn").addEventListener("click", onInsightsButton);
  byId("insights-quick-btn").addEventListener("click", showQuickInsights);
}
