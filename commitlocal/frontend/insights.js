// insights.js — the "Financial insights" card at the bottom of the Money tab.
// Opening the tab only READS what's saved (GET /api/insights): the 50/30/20 check-up (plain maths, no AI)
// and the last AI analysis. The AI (Groq, on our server) is only asked when the user taps the button,
// and the server decides whether a new analysis is really needed. The button is disabled while it runs.
// Uses STATUS_KEYS / STATUS_CLASSES from targets-tab.js (loaded before this file).

// ===== STATE =====
let insightsData = null;   // last reply from the server
let insightsMonth = null;  // month the card is showing
let insightsBusy = false;  // true while a "Generate" request runs

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
  drawCheckupNotes(data.analysis);
  drawInsightGoals(data.analysis.goals);
  drawAiAnalysis(data.saved);
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
      makeElement("span", "item-sub", row.amount === null ? t("insights.notGiven") : formatMoney(Math.round(row.amount))));
    const right = makeElement("div", "split-numbers");
    const actual = row.percent === null ? "—" : Math.round(row.percent) + "%";
    right.append(makeElement("span", "item-name", t("insights.actualVsAim", { actual: actual, aim: row.target_percent })),
      makeElement("span", "item-sub", describeDifference(row)));
    line.append(left, right);
    box.append(line);
  });
}

// Not given → "not given yet"; no income → "add income to compare"; loans unknown → "loans not included"
function describeDifference(row) {
  const points = row.difference_points;
  if (row.amount === null) return t("insights.notGiven");
  if (row.percent === null) return t("insights.noIncomeShort");
  if (points === null) return t("insights.loansUnknown");
  const rounded = Math.round(points);
  if (rounded === 0) return t("insights.onAim");
  return t(rounded > 0 ? "insights.pointsAbove" : "insights.pointsBelow", { n: Math.abs(rounded) });
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
    const sub = t("insights.goalLine", { percent: Math.round(goal.percent),
      amount: formatMoney(Math.round(goal.needs_per_month)) });
    li.append(top, bar, makeElement("span", "item-sub", sub));
    list.append(li);
  });
}

// ===== SAVED AI ANALYSIS =====
function drawAiAnalysis(saved) {
  const box = byId("insights-ai");
  box.replaceChildren();
  const date = byId("insights-date");
  if (!saved.insight) {
    date.textContent = "";
    box.append(makeElement("p", "muted", t("insights.empty")));
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
  setText(button, data.saved.status === "outdated" ? "insights.refresh" : "insights.generate");
  status.textContent = "";
  let blocked = "";
  if (!data.analysis.enough_for_ai) blocked = t("error.AI_NOT_ENOUGH_DATA"); // nothing given yet: nothing to explain
  else if (!data.ai_configured) blocked = t("insights.notConfigured");
  else if (data.usage.used_today >= data.usage.daily_limit) blocked = t("error.AI_DAILY_LIMIT", { limit: data.usage.daily_limit });
  else if (data.paused_seconds > 0) blocked = t("error.AI_RATE_LIMITED", { seconds: data.paused_seconds });
  if (data.saved.status === "fresh") {
    setText(button, "insights.upToDate"); // same data as last time: asking again would give the same answer
    button.disabled = true;
    return;
  }
  button.disabled = Boolean(blocked);
  status.textContent = blocked;
}

async function generateInsightsNow() {
  if (insightsBusy || !insightsData) return; // a double tap does nothing
  insightsBusy = true;
  drawInsightsButton();
  let problem = "";
  try {
    const data = await generateInsights(insightsMonth);
    insightsBusy = false;
    drawInsights(data);
  } catch (error) {
    problem = error.message; // the maths and the last analysis stay on screen
  } finally {
    insightsBusy = false;
  }
  if (problem) {
    drawInsightsButton();
    byId("insights-status").textContent = problem;
  }
}

// ===== START (called by money-tab.js) =====
function startInsights() {
  byId("insights-btn").addEventListener("click", generateInsightsNow);
}
