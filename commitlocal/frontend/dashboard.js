// dashboard.js — the Dashboard tab (the first tab after logging in). It only DRAWS: every number, graph, score,
// badge and the jar level come from GET /api/dashboard (backend/services/dashboard.py, plain maths, never the AI).
// Opening the tab = one GET. Graphs use Chart.js (drawLoanChart / loanChartOptions from loans-tab.js); offline they
// are hidden. The savings jar is an SVG made of coin elements placed by jar-calc.js (window.JarCalc).
// Texts come from i18n.js: t("key"). Category values stay English (the API needs them); only the display is translated.

// ===== STATE =====
let dashData = null;          // last reply from /api/dashboard
let spendingView = "total";   // "total" or "category" (spending graph switch)
let shownLoanId = "all";      // loan graph: "all" or one loan's id
let shownJarGoalId = null;    // savings jar: which goal
let currentUserName = "";     // set by app.js after /api/auth/me

const CATEGORY_COLOURS = ["#3d8bff", "#38d6ff", "#3ddc84", "#ff9a4a", "#f5c451", "#e58fd6", "#c5a3ff", "#5fd4e0",
  "#ff6b7d"];
const BADGE_ICONS = { FIRST_WEEK: "🥇", BUDGET_KEEPER: "🛡️", CONSISTENT_PLANNER: "📅", SAVINGS_STREAK: "🔥" };
const JAR_SEEN_KEY = "jarSeen."; // + goal id → saved amount last shown (so coins only drop when savings grow)
const SVG_NS = "http://www.w3.org/2000/svg";

// ===== LOAD (one GET, no AI) =====
async function loadDashboard() {
  try {
    dashData = await getDashboard(getTodayText());
    drawDashboard();
    announceNewBadges(dashData.badges.new);
  } catch (error) {
    showToast(error.message, true);
  }
}

function drawDashboard() {
  const data = dashData;
  drawWelcome(data);
  drawBalance(data.balance);
  drawHealth(data.health);
  drawSpendingChart(data.spending);
  drawSavingsChart(data.savings);
  drawLoanSection(data.loans);
  drawRecap(data.recap);
  drawJarSection(data.jar);
  drawWeekly(data.weekly, data.recent_weeks);
  drawBadges(data.badges);
}

// Small helpers
function monthShort(monthText) {
  const [year, month] = monthText.split("-").map(Number);
  return I18n.formatDate(new Date(year, month - 1, 1), { month: "short", year: "2-digit" });
}

function moneyOrDash(amount) {
  return amount === null || amount === undefined ? "—" : formatMoney(Math.round(amount));
}

function makeOption(text, value) {
  const option = makeElement("option", "", text);
  option.value = value;
  return option;
}

function setHidden(id, hidden) {
  byId(id).hidden = hidden;
}

// ===== WELCOME + SHORTCUTS =====
function drawWelcome(data) {
  byId("dash-welcome").textContent = currentUserName
    ? t("dash.welcome", { name: currentUserName.split(" ")[0] }) : t("dash.welcomeNoName");
  byId("dash-date").textContent = I18n.formatDate(new Date(), { weekday: "long", day: "numeric", month: "long" });
  setHidden("dash-start", !data.is_new_user);
}

function goTo(page, action) {
  openPage(page);
  if (action) action();
}

// ===== 1. AVAILABLE THIS MONTH =====
function drawBalance(balance) {
  const amount = byId("dash-balance");
  const state = byId("dash-balance-state");
  const compare = byId("dash-balance-compare");
  if (!balance.available) {
    amount.textContent = "—";
    state.hidden = true;
    compare.textContent = t("dash.balance.missing");
  } else {
    amount.textContent = balance.balance < 0 ? formatOut(balance.balance) : formatMoney(balance.balance);
    amount.classList.toggle("negative", balance.balance < 0);
    state.hidden = false;
    state.className = "status dash-state " + balance.state;
    setText(state, "dash.balance.state." + balance.state);
    compare.textContent = balance.change === null ? t("dash.balance.noCompare")
      : t(balance.change >= 0 ? "dash.balance.up" : "dash.balance.down", { amount: formatMoney(Math.abs(balance.change)) });
    if (balance.excludes_loans) compare.textContent += " " + t("dash.balance.noLoans");
  }
  // Only when something really is put aside (no "Rs 0" for someone who never saved)
  byId("dash-put-aside").hidden = !(balance.put_aside > 0);
  byId("dash-put-aside").textContent = t("dash.balance.putAside", { amount: formatMoney(balance.put_aside) });
}

// ===== 2. HEALTH SCORE =====
function drawHealth(health) {
  const ring = byId("dash-score-ring");
  const list = byId("dash-score-parts");
  list.replaceChildren();
  if (!health.available) {
    ring.style.setProperty("--score", 0);
    byId("dash-score").textContent = "—";
    byId("dash-score-level").textContent = t("dash.health.notEnough");
    byId("dash-score-why").textContent = t("dash.health.notEnoughWhy");
    byId("dash-score-tip").textContent = "";
  } else {
    ring.style.setProperty("--score", health.score);
    ring.dataset.level = health.level;
    byId("dash-score").textContent = health.score;
    byId("dash-score-level").textContent = t("dash.health.level." + health.level);
    byId("dash-score-why").textContent = t("dash.health.helped", { what: t("dash.health.check." + health.strength) });
    byId("dash-score-tip").textContent = health.improve ? "💡 " + t("dash.health.improve." + health.improve) : "";
  }
  health.parts.forEach((part) => list.append(makeScorePart(part)));
}

function makeScorePart(part) {
  const li = makeElement("li", "score-part");
  const top = makeElement("div", "card-head");
  const value = part.points === null ? t("dash.health.skipped") : Math.round(part.points) + " / " + part.weight;
  top.append(makeElement("span", "item-name", t("dash.health.part." + part.part)), makeElement("span", "item-sub", value));
  const bar = makeElement("div", "meter");
  const fill = makeElement("div", "meter-fill");
  fill.style.width = part.points === null ? "0%" : (part.points / part.weight) * 100 + "%";
  bar.append(fill);
  li.append(top, bar);
  if (part.points === null) li.append(makeElement("span", "item-sub", t("dash.health.reason." + part.skipped_reason)));
  return li;
}

// ===== 3. SPENDING PER MONTH =====
function drawSpendingChart(spending) {
  setHidden("dash-spend-empty", spending.available);
  setHidden("dash-spend-body", !spending.available);
  setHidden("dash-spend-toggle", !spending.available);
  if (!spending.available) return;
  const months = spending.months;
  const last = months[months.length - 1];
  byId("dash-spend-latest").textContent = t("dash.spend.latest", { month: formatMonthName(last.month),
    amount: formatMoney(Math.round(last.total)) }) + (last.change_percent === null ? ""
    : " · " + t(last.change_percent >= 0 ? "dash.spend.upBy" : "dash.spend.downBy", { n: Math.abs(Math.round(last.change_percent)) }));
  document.querySelectorAll("[data-spend-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.spendView === spendingView);
    button.setAttribute("aria-pressed", button.dataset.spendView === spendingView);
  });
  const labels = months.map((point) => monthShort(point.month));
  let datasets;
  if (spendingView === "total") {
    datasets = [{ label: t("dash.spend.total"), data: months.map((point) => point.total), backgroundColor: "#ff9a4a",
      borderRadius: 8 }];
  } else {
    const categories = [...new Set(months.flatMap((point) => Object.keys(point.by_category)))];
    datasets = categories.map((category, i) => ({ label: tCategory(category), stack: "spend", borderRadius: 4,
      backgroundColor: CATEGORY_COLOURS[i % CATEGORY_COLOURS.length],
      data: months.map((point) => point.by_category[category] || 0) }));
  }
  const options = loanChartOptions(t("dash.chart.month"));
  options.scales.x.stacked = spendingView === "category";
  options.scales.y.stacked = spendingView === "category";
  options.plugins.tooltip.callbacks.footer = (items) => {
    const point = months[items[0].dataIndex];
    const lines = [t("dash.spend.total") + ": " + formatMoney(point.total)];
    if (point.change_percent !== null) lines.push(t("dash.spend.vsPrevious", { n: Math.round(point.change_percent) }));
    return lines;
  };
  drawLoanChart("dash-spend-chart", { type: "bar", data: { labels: labels, datasets: datasets }, options: options });
}

// ===== 4. SAVING RATE PER MONTH =====
function drawSavingsChart(savings) {
  setHidden("dash-save-empty", savings.available);
  setHidden("dash-save-body", !savings.available);
  if (!savings.available) {
    byId("dash-save-empty-text").textContent = t("dash.save.empty." + savings.reason);
    return;
  }
  const months = savings.months;
  const last = months[months.length - 1];
  byId("dash-save-latest").textContent = t("dash.save.latest", { rate: Math.round(last.rate),
    amount: formatMoney(Math.round(last.saved)) }) + (savings.trend ? " · " + t("dash.save.trend." + savings.trend) : "");
  const options = loanChartOptions(t("dash.chart.month"));
  options.scales.y.title = { display: true, text: "Rs", color: "#9fb0d6" };
  options.scales.y1 = { position: "right", min: 0, grid: { drawOnChartArea: false },
    ticks: { color: "#9fb0d6", callback: (v) => v + "%" } };
  options.plugins.tooltip.callbacks.label = (c) => c.dataset.yAxisID === "y1"
    ? c.dataset.label + ": " + Math.round(c.parsed.y) + "%" : c.dataset.label + ": " + LoanCalc.formatRupees(c.parsed.y);
  drawLoanChart("dash-save-chart", {
    type: "bar",
    data: {
      labels: months.map((point) => monthShort(point.month)),
      datasets: [
        { type: "bar", label: t("dash.save.amount"), data: months.map((p) => p.saved), backgroundColor: "#3ddc84",
          borderRadius: 8, yAxisID: "y" },
        { type: "line", label: t("dash.save.rate"), data: months.map((p) => p.rate), borderColor: "#38d6ff",
          pointRadius: 4, tension: 0.2, yAxisID: "y1" },
        { type: "line", label: t("dash.save.guide", { n: savings.guide }), data: months.map(() => savings.guide),
          borderColor: "#f5c451", borderDash: [6, 4], pointRadius: 0, yAxisID: "y1" },
      ],
    },
    options: options,
  });
}

// ===== 5. LOAN PROJECTION =====
function drawLoanSection(loans) {
  setHidden("dash-loan-empty", loans.available);
  setHidden("dash-loan-body", !loans.available);
  if (!loans.available) {
    byId("dash-loan-empty-text").textContent = t(loans.state === "none" ? "dash.loan.none" : "dash.loan.empty");
    return;
  }
  const select = byId("dash-loan-select");
  select.replaceChildren();
  if (loans.loans.length > 1) select.append(makeOption(t("dash.loan.all"), "all"));
  loans.loans.forEach((loan) => select.append(makeOption(loan.name || t("loan.unnamed"), loan.id)));
  if (![...select.options].some((option) => option.value === shownLoanId)) shownLoanId = select.options[0].value;
  select.value = shownLoanId;
  select.hidden = loans.loans.length < 2;
  drawLoanChoice(loans);
}

function drawLoanChoice(loans) {
  const loan = shownLoanId === "all" ? null : loans.loans.find((item) => item.id === shownLoanId);
  const points = loan ? loan.points : loans.total;
  const note = byId("dash-loan-note");
  byId("dash-loan-outstanding").textContent = t("dash.loan.outstanding", {
    amount: formatMoney(loan ? loan.balance : loans.outstanding),
    payment: formatMoney(loan ? loan.monthly_payment : loans.monthly_payments) });
  if (!points || (loan && !loan.available)) {
    byId("dash-loan-chart").parentElement.hidden = true;
    const reason = loan ? loan.reason : loans.loans.find((item) => !item.available).reason;
    note.textContent = t("dash.loan.unavailable." + reason);
    byId("dash-loan-payoff").textContent = "";
    return;
  }
  const payoff = loan ? loan.payoff_month : points[points.length - 1].month;
  byId("dash-loan-payoff").textContent = t("dash.loan.payoff", { month: formatMonthName(payoff) });
  note.textContent = t("dash.loan.estimate");
  drawLoanChart("dash-loan-chart", {
    type: "line",
    data: {
      labels: points.map((point) => monthShort(point.month)),
      datasets: [{ label: t("dash.loan.projected"), data: points.map((point) => point.balance), borderColor: "#3d8bff",
        backgroundColor: "rgba(61, 139, 255, 0.16)", borderDash: [6, 4], fill: true, pointRadius: 0, tension: 0.2 }],
    },
    options: loanChartOptions(t("dash.chart.month")),
  });
}

// ===== 6. MONTHLY RECAP (sentences are fixed templates chosen by the backend) =====
function drawRecap(recap) {
  byId("dash-recap-month").textContent = formatMonthName(recap.month);
  byId("dash-recap-income").textContent = recap.income === null ? "—" : formatIn(Math.round(recap.income));
  byId("dash-recap-expenses").textContent = recap.expenses === null ? "—" : formatOut(Math.round(recap.expenses));
  byId("dash-recap-savings").textContent = moneyOrDash(recap.savings);
  byId("dash-recap-loans").textContent = moneyOrDash(recap.loan_repayments);
  byId("dash-recap-left").textContent = moneyOrDash(recap.remaining);
  byId("dash-recap-top").textContent = recap.biggest_category
    ? tCategory(recap.biggest_category.category) + " · " + formatMoney(recap.biggest_category.amount) : "—";
  const progress = recap.savings_progress;
  byId("dash-recap-progress").textContent = progress.percent === null ? "—"
    : t("common.amountOf", { a: formatMoney(progress.saved), b: formatMoney(progress.target) });
  const list = byId("dash-recap-text");
  list.replaceChildren();
  recap.statements.forEach((line) => {
    const params = Object.assign({}, line.params);
    if (typeof params.amount === "number") params.amount = formatMoney(params.amount);
    if (params.category) params.category = tCategory(params.category);
    list.append(makeElement("li", "", t("dash.recap." + line.code, params)));
  });
  if (recap.statements.length === 0) list.append(makeElement("li", "muted", t("dash.recap.empty")));
}

// ===== 7. SAVINGS JAR (coins = real goal progress) =====
function drawJarSection(jar) {
  setHidden("dash-jar-empty", jar.available);
  setHidden("dash-jar-body", !jar.available);
  if (!jar.available) return;
  if (!jar.goals.some((goal) => goal.id === shownJarGoalId)) shownJarGoalId = jar.goals[0].id;
  const chips = byId("dash-jar-goals");
  chips.replaceChildren();
  jar.goals.forEach((goal) => {
    const chip = makeButton(goal.name, "chip" + (goal.id === shownJarGoalId ? " active" : ""), () => {
      shownJarGoalId = goal.id;
      drawJarSection(dashData.jar);
    });
    chip.setAttribute("aria-pressed", goal.id === shownJarGoalId);
    chips.append(chip);
  });
  const goal = jar.goals.find((item) => item.id === shownJarGoalId);
  drawJar(goal, readJarSeen(goal.id));
  writeJarSeen(goal.id, goal.saved);
  byId("dash-jar-name").textContent = goal.name;
  byId("dash-jar-saved").textContent = formatMoney(goal.saved);
  byId("dash-jar-target").textContent = formatMoney(goal.target);
  byId("dash-jar-remaining").textContent = formatMoney(goal.remaining);
  byId("dash-jar-percent").textContent = Math.round(goal.percent) + "%";
  byId("dash-jar-message").textContent = goal.percent >= 100 ? "🎉 " + t("dash.jar.done")
    : goal.saved > 0 ? t("dash.jar.some") : t("dash.jar.nothing");
}

// Remember which amount the jar showed last, so coins only drop in when savings really grow (not on every visit)
function readJarSeen(goalId) {
  try {
    const value = localStorage.getItem(JAR_SEEN_KEY + goalId);
    return value === null ? null : Number(value);
  } catch (error) {
    return null; // private window: just no animation
  }
}

function writeJarSeen(goalId, saved) {
  try {
    localStorage.setItem(JAR_SEEN_KEY + goalId, String(saved));
  } catch (error) {
    // storage blocked: fine
  }
}

function svgElement(tag, attributes) {
  const element = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
  return element;
}

const JAR_OUTLINE = "M65 30 L65 42 C65 52 28 56 28 78 L28 206 Q28 226 48 226 L152 226 Q172 226 172 206 L172 78 " +
  "C172 56 135 52 135 42 L135 30 Z";
const JAR_INSIDE = "M69 34 L69 44 C69 56 32 60 32 80 L32 204 Q32 222 50 222 L150 222 Q168 222 168 204 L168 80 " +
  "C168 60 131 56 131 44 L131 34 Z";

// previousSaved = amount shown last time (null = first time: no drop animation)
function drawJar(goal, previousSaved) {
  const box = byId("dash-jar");
  box.replaceChildren();
  const root = svgElement("svg", { viewBox: "0 0 200 240", class: "jar-svg" + (goal.percent >= 100 ? " jar-done" : ""),
    role: "img", "aria-label": t("dash.jar.aria", { name: goal.name, percent: Math.round(goal.percent) }) });
  const defs = svgElement("defs", {});
  const gold = svgElement("radialGradient", { id: "coin-gold", cx: "40%", cy: "35%", r: "70%" });
  gold.append(svgElement("stop", { offset: "0%", "stop-color": "#fff1a8" }),
    svgElement("stop", { offset: "55%", "stop-color": "#f2c14e" }), svgElement("stop", { offset: "100%", "stop-color": "#b9811c" }));
  const clip = svgElement("clipPath", { id: "jar-inside" });
  clip.append(svgElement("path", { d: JAR_INSIDE }));
  defs.append(gold, clip);
  root.append(defs, svgElement("path", { d: JAR_OUTLINE, class: "jar-glass" }));

  // Coins: only the ones above the old amount drop in, the rest are already in place
  let fromCount;
  if (previousSaved !== null && goal.saved > previousSaved && goal.target > 0) {
    fromCount = JarCalc.coinCount((previousSaved / goal.target) * 100);
  }
  const coins = svgElement("g", { "clip-path": "url(#jar-inside)" });
  let dropNumber = 0;
  JarCalc.layoutCoins(goal.percent, fromCount).forEach((coin) => {
    const place = svgElement("g", { transform: "translate(" + coin.x + " " + coin.y + ") rotate(" + coin.rotate + ")" });
    const body = svgElement("g", { class: coin.isNew ? "coin coin-drop" : "coin" });
    if (coin.isNew) {
      body.style.setProperty("--drop", -(coin.y - 8) + "px");
      body.style.animationDelay = Math.min(dropNumber, 20) * 70 + "ms";
      dropNumber += 1;
    }
    body.append(svgElement("ellipse", { rx: 13, ry: 5.5, fill: "url(#coin-gold)", stroke: "#a8740f", "stroke-width": 1 }),
      svgElement("ellipse", { rx: 8, ry: 2.8, fill: "none", stroke: "#fff6cc", "stroke-width": 0.8, opacity: 0.7 }));
    place.append(body);
    coins.append(place);
  });
  root.append(coins);
  // Glass shine + rim drawn on top, so the coins look inside the jar
  root.append(svgElement("path", { d: "M46 100 C43 125 43 150 46 170", class: "jar-shine" }),
    svgElement("rect", { x: 58, y: 20, width: 84, height: 13, rx: 5, class: "jar-rim" }));
  if (goal.percent >= 100) { // small celebration
    const sparkles = svgElement("g", { class: "jar-sparkles" });
    [[40, 24], [162, 30], [100, 8], [178, 70], [22, 66]].forEach(([x, y], i) => {
      const star = svgElement("circle", { cx: x, cy: y, r: 3.5 });
      star.style.animationDelay = i * 180 + "ms";
      sparkles.append(star);
    });
    root.append(sparkles);
  }
  box.append(root);
}

// ===== 8. WEEKLY BUDGET + BADGES =====
function drawWeekly(weekly, recentWeeks) {
  byId("dash-week-input").value = weekly.budget === null ? "" : weekly.budget;
  setHidden("dash-week-remove", !weekly.available);
  setHidden("dash-week-body", !weekly.available);
  byId("dash-week-note").textContent = weekly.available ? "" : t("dash.week.setOne");
  if (!weekly.available) return;
  const bar = byId("dash-week-bar");
  bar.style.width = Math.min(weekly.percent, 100) + "%";
  bar.parentElement.classList.toggle("over", weekly.state === "over");
  byId("dash-week-text").textContent = t(weekly.state === "over" ? "dash.week.over" : "dash.week.left", {
    spent: formatMoney(weekly.spent), budget: formatMoney(weekly.budget), left: formatMoney(Math.abs(weekly.left)) });
  byId("dash-week-days").textContent = t("dash.week.days", { left: weekly.days_left, recorded: weekly.days_recorded,
    min: weekly.min_tracked_days });
  const list = byId("dash-week-history");
  list.replaceChildren();
  recentWeeks.slice().reverse().forEach((week) => {
    const result = week.kept ? "dash.week.kept" : week.tracked ? "dash.week.missed" : "dash.week.notTracked";
    list.append(makeElement("li", "", formatShortDate(week.week_start) + " – " + formatShortDate(week.week_end) + ": " +
      t(result, { spent: formatMoney(week.spent) })));
  });
}

function drawBadges(badges) {
  const earned = {};
  badges.earned.forEach((badge) => { earned[badge.code] = badge.earned_on; });
  const list = byId("dash-badges");
  list.replaceChildren();
  badges.all.forEach((code) => {
    const li = makeElement("li", "badge" + (earned[code] ? " earned" : ""));
    li.append(makeElement("span", "badge-icon", earned[code] ? BADGE_ICONS[code] : "🔒"),
      makeElement("span", "item-name", t("dash.badge." + code + ".name")),
      makeElement("span", "item-sub", t("dash.badge." + code + ".desc")),
      makeElement("span", "item-sub", earned[code] ? t("dash.badge.earnedOn", { date: formatShortDate(earned[code]) })
        : t("dash.badge.notYet")));
    list.append(li);
  });
}

function announceNewBadges(codes) {
  if (codes.length) showToast(t("dash.badge.new", { name: codes.map((code) => t("dash.badge." + code + ".name")).join(", ") }));
}

async function saveWeeklyBudget(event) {
  event.preventDefault();
  const text = byId("dash-week-input").value;
  const amount = Number(text);
  if (text === "" || !(amount > 0) || amount > 10000000) { // same rule as the backend (more than 0, at most 1 crore)
    byId("dash-week-error").textContent = t("dash.week.bad");
    return;
  }
  await sendWeeklyBudget(amount);
}

async function sendWeeklyBudget(amount) {
  byId("dash-week-error").textContent = "";
  try {
    dashData = await setWeeklyBudget(amount, getTodayText());
    drawDashboard();
    showToast(t(amount === null ? "dash.week.removed" : "dash.week.saved"));
  } catch (error) {
    byId("dash-week-error").textContent = error.message;
  }
}

// ===== LANGUAGE SWITCH (called by app.js) =====
function redrawDashboard() {
  if (dashData) drawDashboard();
}

// ===== START (called by app.js once you're logged in) =====
function startDashboard() {
  document.querySelectorAll("[data-spend-view]").forEach((button) => {
    button.addEventListener("click", () => {
      spendingView = button.dataset.spendView;
      drawSpendingChart(dashData.spending);
    });
  });
  byId("dash-loan-select").addEventListener("change", (event) => {
    shownLoanId = event.target.value;
    drawLoanChoice(dashData.loans);
  });
  byId("dash-week-form").addEventListener("submit", saveWeeklyBudget);
  byId("dash-week-remove").addEventListener("click", () => sendWeeklyBudget(null));
  byId("dash-details-btn").addEventListener("click", () => goTo("money"));
  byId("dash-add-income").addEventListener("click", () => goTo("money", () => openIncomeSheet(null, "monthly")));
  byId("dash-add-expense").addEventListener("click", () => goTo("money", () => openExpenseSheet(null)));
  byId("dash-add-goal").addEventListener("click", () => goTo("targets", () => openGoalSheet(null)));
  byId("dash-add-loan").addEventListener("click", () => goTo("loans", () => byId("repay-balance").focus()));
  byId("dash-jar-new").addEventListener("click", () => goTo("targets", () => openGoalSheet(null)));
  byId("dash-loan-add").addEventListener("click", () => goTo("loans", () => byId("repay-balance").focus()));
  byId("dash-save-add").addEventListener("click", () => goTo("targets"));
  byId("dash-spend-add").addEventListener("click", () => goTo("money", () => openExpenseSheet(null)));
  loadDashboard();
}
