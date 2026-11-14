// dashboard.js — the Dashboard tab (the first page after logging in). It only DRAWS: every number, graph, score
// and jar level come from GET /api/dashboard (backend/services/dashboard.py, plain maths, never the AI).
// The page is a 2-column grid of blocks: each starts as a small tile (icon + title + one number); tapping it opens
// the full block across both columns (only one open at a time, remembered in localStorage "dashOpenBlock").
// Opening the tab = one GET. Graphs use Chart.js (drawLoanChart / loanChartOptions from loans-tab.js); offline they
// are hidden. The savings jars are SVGs (liquid + wave + coins) measured by jar-calc.js (window.JarCalc).
// The weekly budget + badges are drawn on the Profile tab (profile-tab.js) from the same GET.
// Texts come from i18n.js: t("key"). Category values stay English (the API needs them); only the display is translated.

// ===== STATE =====
let dashData = null;          // last reply from /api/dashboard
let spendingView = "total";   // "total" or "category" (spending graph switch)
let shownLoanId = "all";      // loan graph: "all" or one loan's id
let openBlockName = null;     // which Dashboard block is open (null = all are small tiles)
let currentUserName = "";     // set by app.js after /api/auth/me

const CATEGORY_COLOURS = ["#3d8bff", "#38d6ff", "#3ddc84", "#ff9a4a", "#f5c451", "#e58fd6", "#c5a3ff", "#5fd4e0",
  "#ff6b7d"];
const JAR_SEEN_KEY = "jarSeen."; // + goal id → saved amount last shown (so the jar only fills up when savings grow)
const OPEN_BLOCK_KEY = "dashOpenBlock"; // the last open block (per phone)
const BLOCK_OPEN_MS = 260;      // a little longer than the 250 ms opening animation in style.css
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
  drawTiles(data);
  drawBalance(data.balance);
  drawHealth(data.health);
  drawSpendingChart(data.spending);
  drawSavingsChart(data.savings);
  drawLoanSection(data.loans);
  drawRecap(data.recap);
  drawJarSection(data.jar);
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

// ===== THE GRID: SMALL TILES THAT OPEN INTO FULL BLOCKS =====
// One key number per tile. Missing data shows "—" (or "Not shared 🔒"), never Rs 0.
function drawTiles(data) {
  const balance = data.balance;
  byId("tile-balance").textContent = !balance.available ? "—"
    : balance.balance < 0 ? formatOut(Math.round(balance.balance)) : formatMoney(Math.round(balance.balance));
  byId("tile-score").textContent = data.health.available ? data.health.score : "—";
  byId("tile-spend").textContent = data.recap.expenses === null ? "—" : formatMoney(Math.round(data.recap.expenses));
  const saving = data.savings;
  byId("tile-save").textContent = saving.available ? Math.round(saving.months[saving.months.length - 1].rate) + "%" : "—";
  byId("tile-jar").textContent = data.jar.overall_percent === null ? "—" : Math.round(data.jar.overall_percent) + "%";
  const loans = data.loans;
  byId("tile-loans").textContent = loans.available ? formatMoney(Math.round(loans.outstanding))
    : loans.state === "none" ? t("dash.tile.noLoans") : t("dash.tile.notShared");
  byId("tile-recap").textContent = I18n.formatDate(new Date(data.recap.month + "-01T12:00:00"), { month: "long" });
}

function readOpenBlock() {
  try {
    return localStorage.getItem(OPEN_BLOCK_KEY);
  } catch (error) {
    return null; // storage blocked: everything starts closed
  }
}

function saveOpenBlock(name) {
  try {
    if (name) localStorage.setItem(OPEN_BLOCK_KEY, name);
    else localStorage.removeItem(OPEN_BLOCK_KEY);
  } catch (error) {
    // storage blocked: fine
  }
}

// Tap a tile: open it (and close the others), or close it if it was already open
function toggleBlock(name) {
  openBlock(openBlockName === name ? null : name, true);
}

function openBlock(name, byTap) {
  if (name && !byId("block-" + name)) name = null; // an old saved name that no longer exists
  openBlockName = name;
  document.querySelectorAll(".dash-block").forEach((block) => {
    const isOpen = block.dataset.block === name;
    block.classList.toggle("open", isOpen);
    block.querySelector(".dash-tile").setAttribute("aria-expanded", isOpen);
  });
  saveOpenBlock(name);
  if (name) setTimeout(() => afterBlockOpened(name, byTap), prefersLessMotion() ? 0 : BLOCK_OPEN_MS);
}

// Graphs drawn while the block was small get the full width now; the jar plays its "money added" animation now
function afterBlockOpened(name, byTap) {
  const block = byId("block-" + name);
  block.querySelectorAll("canvas").forEach((canvas) => {
    if (loanCharts[canvas.id]) loanCharts[canvas.id].resize(); // loanCharts: loans-tab.js
  });
  if (name === "jar" && dashData && dashData.jar.available) drawJarList(dashData.jar, true);
  if (byTap) block.scrollIntoView({ block: "nearest", behavior: prefersLessMotion() ? "auto" : "smooth" });
}

function setUpBlocks() {
  document.querySelectorAll(".dash-block").forEach((block) => {
    block.querySelector(".dash-tile").addEventListener("click", () => toggleBlock(block.dataset.block));
  });
  openBlock(readOpenBlock(), false);
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

// ===== 7. SAVINGS JARS (one per goal, liquid level = real goal progress) =====
function drawJarSection(jar) {
  setHidden("dash-jar-empty", jar.available);
  setHidden("dash-jar-body", !jar.available);
  if (!jar.available) return;
  // While the block is closed nobody sees the jar, so the "money added" animation waits until it opens
  drawJarList(jar, openBlockName === "jar");
}

// visible = the jar block is open: play the rise + coin for goals that grew, and remember what was shown
function drawJarList(jar, visible) {
  const list = byId("dash-jar-list");
  list.replaceChildren();
  jar.goals.forEach((goal, index) => {
    const previous = readJarSeen(goal.id);
    const animate = visible && !prefersLessMotion() && JarCalc.shouldAnimate(previous, goal.saved);
    list.append(makeJarCard(goal, animate ? previous : null, index));
    if (visible) writeJarSeen(goal.id, goal.saved);
  });
}

function makeJarCard(goal, previousSaved, index) {
  const percent = Math.round(goal.percent);
  const card = makeButton("", "jar-card", () => openSavingsView(goal.id)); // money-tab.js: Money → Savings
  card.setAttribute("aria-label", t("dash.jar.aria", { name: goal.name, percent: percent }) + ". " + t("dash.jar.open"));
  card.append(makeElement("span", "jar-name", goal.name));
  const box = makeElement("span", "jar-box");
  box.append(drawJar(goal, previousSaved, index));
  card.append(box);
  card.append(makeElement("span", "jar-amounts", t("dash.jar.amounts", { a: formatMoney(goal.saved),
    b: formatMoney(goal.target), n: percent })));
  if (goal.percent >= 100) card.append(makeElement("span", "jar-done-text", t("dash.jar.reached")));
  return card;
}

// Remember which amount the jar showed last, so it only fills up when savings really grow (not on every visit)
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

function makeGradient(id, stops) {
  const gradient = svgElement("linearGradient", { id: id, x1: "0", y1: "0", x2: "0", y2: "1" });
  stops.forEach(([offset, colour]) => gradient.append(svgElement("stop", { offset: offset, "stop-color": colour })));
  return gradient;
}

// The liquid level, moved with a CSS transform (SVG units). previousSaved !== null → rise from the old level.
function makeLiquid(goal, previousSaved, n) {
  const level = svgElement("g", { class: "jar-liquid" });
  const endY = JarCalc.levelY(goal.percent);
  level.style.transform = "translateY(" + endY + "px)";
  if (previousSaved !== null) { // CSS animation jar-rise (style.css) slides from the old level to the new one
    level.style.setProperty("--from-y", JarCalc.levelY((previousSaved / goal.target) * 100) + "px");
    level.style.setProperty("--to-y", endY + "px");
    level.classList.add("jar-rising");
  }
  level.append(svgElement("path", { d: JarCalc.wavePath(), class: "jar-wave jar-wave-back", fill: "url(#jar-liquid-" + n + ")" }),
    svgElement("path", { d: JarCalc.wavePath(), class: "jar-wave jar-wave-front", fill: "url(#jar-liquid-" + n + ")" }));
  return level;
}

function makeCoin(coin, n) {
  const place = svgElement("g", { transform: "translate(" + coin.x + " " + coin.y + ") rotate(" + coin.rotate + ")" });
  const body = svgElement("g", { class: "coin" });
  body.append(svgElement("ellipse", { rx: 12, ry: 5, fill: "url(#coin-gold-" + n + ")", stroke: "#a8740f", "stroke-width": 1 }),
    svgElement("ellipse", { rx: 7.5, ry: 2.6, fill: "none", stroke: "#fff6cc", "stroke-width": 0.8, opacity: 0.7 }));
  place.append(body);
  return { place: place, body: body };
}

// n = the jar's number on the page (each SVG needs its own gradient / clip ids)
function drawJar(goal, previousSaved, n) {
  const root = svgElement("svg", { viewBox: "0 0 200 240", class: "jar-svg" + (goal.percent >= 100 ? " jar-done" : ""),
    "aria-hidden": "true", focusable: "false" });
  const defs = svgElement("defs", {});
  const gold = svgElement("radialGradient", { id: "coin-gold-" + n, cx: "40%", cy: "35%", r: "70%" });
  gold.append(svgElement("stop", { offset: "0%", "stop-color": "#fff1a8" }),
    svgElement("stop", { offset: "55%", "stop-color": "#f2c14e" }), svgElement("stop", { offset: "100%", "stop-color": "#b9811c" }));
  const clip = svgElement("clipPath", { id: "jar-inside-" + n });
  clip.append(svgElement("path", { d: JAR_INSIDE }));
  defs.append(gold, clip, makeGradient("jar-liquid-" + n, [["0%", "#5fe3ff"], ["100%", "#2a6dff"]]));
  root.append(defs, svgElement("path", { d: JAR_OUTLINE, class: "jar-glass" }));

  const inside = svgElement("g", { "clip-path": "url(#jar-inside-" + n + ")" });
  if (goal.percent > 0) inside.append(makeLiquid(goal, previousSaved, n));
  const coins = JarCalc.layoutCoins(goal.percent);
  coins.forEach((spot, i) => {
    const coin = makeCoin(spot, n);
    if (previousSaved !== null && i === coins.length - 1) { // one coin drops in when money was added
      coin.body.classList.add("coin-drop");
      coin.body.style.setProperty("--drop", -(spot.y - 40) + "px");
    }
    inside.append(coin.place);
  });
  root.append(inside);
  // Glass shine + rim on top, so the liquid looks inside the jar
  root.append(svgElement("path", { d: "M46 100 C43 125 43 150 46 170", class: "jar-shine" }),
    svgElement("rect", { x: 58, y: 20, width: 84, height: 13, rx: 5, class: "jar-rim" }));
  if (goal.percent >= 100) { // short celebration
    const sparkles = svgElement("g", { class: "jar-sparkles" });
    [[40, 24], [162, 30], [100, 8], [178, 70], [22, 66], [60, 6], [140, 10]].forEach(([x, y], i) => {
      const star = svgElement("circle", { cx: x, cy: y, r: 3.5 });
      star.style.animationDelay = i * 140 + "ms";
      sparkles.append(star);
    });
    root.append(sparkles);
  }
  return root;
}

function announceNewBadges(codes) {
  if (codes.length) showToast(t("dash.badge.new", { name: codes.map((code) => t("dash.badge." + code + ".name")).join(", ") }));
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
  byId("dash-details-btn").addEventListener("click", () => goTo("money"));
  byId("dash-add-income").addEventListener("click", () => goTo("money", () => openIncomeSheet(null, "monthly")));
  byId("dash-add-expense").addEventListener("click", () => goTo("money", () => openExpenseSheet(null)));
  byId("dash-add-goal").addEventListener("click", () => openSavingsView().then(() => openGoalSheet(null)));
  byId("dash-add-loan").addEventListener("click", () => goTo("loans", () => byId("repay-balance").focus()));
  byId("dash-jar-new").addEventListener("click", () => openSavingsView().then(() => openGoalSheet(null)));
  byId("dash-loan-add").addEventListener("click", () => goTo("loans", () => byId("repay-balance").focus()));
  byId("dash-save-add").addEventListener("click", () => openSavingsView());
  byId("dash-spend-add").addEventListener("click", () => goTo("money", () => openExpenseSheet(null)));
  setUpBlocks();
  loadDashboard();
}
