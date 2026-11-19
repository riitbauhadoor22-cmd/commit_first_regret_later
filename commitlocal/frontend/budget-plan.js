// budget-plan.js — the "My budget plan" card on the Money tab and its pop-ups: the start questions, "Change plan"
// (looser / stricter, with the cost of a looser plan and a second confirm) and "Why this plan?" (reason, research,
// history). Every rule (next-month changes, one change a month, no loosening for wants) is checked by the backend
// (routes/plan.py); this file only shows the result. Texts: plan.* in lang/*.json.

// ===== STATE =====
let planState = null;   // the last GET /api/plan reply
let startLife = null;   // "studying" / "working" / "both" in the start questions
let looserStep = null;  // {planId, reason <select>} while the looser-plan friction is on screen

const PLAN_REASONS = ["rent_up", "lost_income", "loan_up", "other"];

// ===== SMALL HELPERS =====
function planName(planId) { return t("plan." + planId + ".name"); }

function planPlan(planId) {
  return planState.plans.find((plan) => plan.id === planId);
}

// "aim 60 · 30 · 10"
function planAimText(plan) {
  return t("money.aimPlan", { needs: plan.needs, wants: plan.wants, savings: plan.savings });
}

// "2026-12" → "1 Dec"
function firstOfMonth(month) { return formatShortDate(month + "-01"); }

// ["2026-10", "2026-11"] → "October 2026, November 2026"
function monthList(months) { return (months || []).map(formatMonthName).join(", "); }

function planButton(className, key, onClick, params) {
  const button = makeTextElement("button", className, key, params);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

// ===== THE CARD =====
async function loadPlanCard() {
  try {
    planState = await getPlan(getTodayText());
  } catch (error) {
    return; // the rest of the Money tab still works; the toast comes from loadMoneyTab
  }
  drawPlanCard();
}

function drawPlanCard() {
  const body = byId("plan-body");
  byId("plan-why-btn").hidden = !planState.has_plan;
  if (!planState.has_plan) {
    body.replaceChildren(makeTextElement("p", "muted", "plan.noPlan"),
      planButton("btn", "plan.choose", openPlanStart));
    return;
  }
  const plan = planPlan(planState.current.plan_id);
  const items = [makeElement("p", "plan-name", planName(plan.id)), makeElement("p", "aim", planAimText(plan))];
  items.push(drawPlanProgress(plan));
  const savingsBox = makeElement("div", "stack");
  savingsBox.append(...makeSavingsStatus(planState.savings_status)); // same message as the Money card
  items.push(savingsBox);
  if (planState.streak > 0) items.push(makeTextElement("p", "plan-streak", "plan.streak", { n: planState.streak }));
  if (planState.pending) items.push(drawPendingLine());
  if (planState.last_result) items.push(drawLastResult(planState.last_result));
  const advice = drawRecommendation(planState.recommendation);
  if (advice) items.push(advice);
  const actions = makeElement("div", "info-actions");
  actions.append(planButton("btn btn-small btn-light", "plan.changeButton", openPlanChange));
  items.push(actions);
  body.replaceChildren(...items);
}

// This month so far: "Needs 42% · aim 50%" per part (no income yet → a short note instead)
function drawPlanProgress(plan) {
  const progress = planState.progress;
  if (!progress) return makeTextElement("p", "muted small", "plan.progressNeedsIncome");
  const list = makeElement("div", "split-table");
  ["needs", "wants", "savings"].forEach((part) => {
    const row = progress[part];
    const line = makeElement("p", "split-row");
    if (row.actual === null) { // savings never added: "not tracked yet", never a red 0%
      line.append(makeTextElement("span", "", "plan.part." + part), makeTextElement("span", "muted", "plan.notTracked"));
      list.append(line);
      return;
    }
    const over = part === "savings" ? row.actual < row.aim : row.actual > row.aim;
    line.classList.toggle("warn", over);
    line.append(makeTextElement("span", "", "plan.part." + part),
      makeTextElement("span", "", "insights.actualVsAim", { actual: Math.round(row.actual) + "%", aim: row.aim }));
    list.append(line);
  });
  return list;
}

function drawPendingLine() {
  const box = makeElement("div", "tip");
  box.append(makeTextElement("p", "", "plan.pending",
    { plan: planName(planState.pending.plan_id), date: firstOfMonth(planState.pending.start_month) }));
  box.append(planButton("link-btn", "plan.cancelPending", cancelPendingPlan));
  return box;
}

// Last month: on plan, or over (which part, by how much) + 1–2 tips. Never a "pick a looser plan" tip.
function drawLastResult(result) {
  const box = makeElement("div", "stack");
  if (result.status === "on_plan") {
    box.append(makeTextElement("p", "", "plan.result.onPlan", { month: formatMonthName(result.month) }));
    return box;
  }
  if (result.status === "no_data") {
    box.append(makeTextElement("p", "muted", "plan.result.noData", { month: formatMonthName(result.month) }));
    return box;
  }
  const parts = [];
  if (result.wants_over) parts.push(t("plan.over.wants", { amount: formatMoney(result.wants_over) }));
  if (result.needs_over) parts.push(t("plan.over.needs", { amount: formatMoney(result.needs_over) }));
  if (result.savings_short) parts.push(t("plan.over.savings", { amount: formatMoney(result.savings_short) }));
  box.append(makeElement("p", "", t("plan.result.over", { month: formatMonthName(result.month) }) + " " + parts.join(", ") + "."));
  (result.tips || []).forEach((tip) => {
    const params = { amount: tip.amount ? formatMoney(tip.amount) : "", cap: tip.cap !== undefined ? formatMoney(tip.cap) : "",
      category: tip.category ? tCategory(tip.category) : "" };
    box.append(makeElement("p", "tip-line", "• " + t("plan.tip." + tip.code, params)));
  });
  return box;
}

// The once-a-month suggestion (switch / caps / keep / wait)
function drawRecommendation(advice) {
  if (!advice) return null;
  if (advice.action === "wait") return makeTextElement("p", "muted small", "plan.rec.wait");
  const numbers = { ...advice.numbers, months: monthList(advice.numbers && advice.numbers.months),
    lowest: advice.numbers && advice.numbers.lowest ? formatMoney(advice.numbers.lowest) : "",
    highest: advice.numbers && advice.numbers.highest ? formatMoney(advice.numbers.highest) : "" };
  if (advice.action === "keep") {
    // WANTS_OVER: a style with more room for wants isn't suggested while wants are above the current plan
    return makeTextElement("p", "muted small", advice.rule === "WANTS_OVER" ? "plan.rec.WANTS_OVER" : "plan.rec.keep");
  }
  const box = makeElement("div", "warning-box stack");
  if (advice.action === "caps") {
    box.append(makeTextElement("p", "", "plan.rec.WANTS_HIGH", numbers));
    advice.caps.slice(0, 3).forEach((cap) => {
      box.append(makeElement("p", "tip-line", "• " + t("plan.capLine", { category: tCategory(cap.category), cap: formatMoney(cap.cap) })));
    });
    return box;
  }
  box.append(makeElement("p", "", t("plan.rec.suggested", { plan: planName(advice.plan_id) }) + " " +
    t("plan.rec." + advice.rule, numbers)));
  const actions = makeElement("div", "info-actions");
  actions.append(planButton("btn btn-small", "plan.rec.switch", () => acceptRecommendation(advice.plan_id),
    { date: firstOfMonth(planState.next_month) }));
  actions.append(planButton("btn btn-small btn-light", "plan.rec.keepMine", () => { box.hidden = true; }));
  box.append(actions);
  return box;
}

async function acceptRecommendation(planId) {
  await sendPlanChange({ plan_id: planId, from_recommendation: true });
}

async function cancelPendingPlan() {
  try {
    planState = await cancelPlanChange(getTodayText());
    drawPlanCard();
    showToast(t("plan.cancelled"));
  } catch (error) {
    showToast(error.message, true);
  }
}

// ===== START QUESTIONS (first plan only) =====
function openPlanStart() {
  startLife = null;
  byId("plan-start-form").reset();
  byId("plan-start-form").hidden = false;
  byId("plan-start-result").hidden = true;
  byId("plan-start-error").textContent = "";
  document.querySelectorAll("[data-life]").forEach((b) => b.classList.remove("active"));
  openSheet("sheet-plan-start");
}

function readStartAnswers() {
  return { life: startLife, pays_rent: byId("plan-rent").checked, has_loan: byId("plan-loan").checked,
    irregular_income: byId("plan-irregular").checked, today: getTodayText() };
}

async function suggestStartPlan(event) {
  event.preventDefault();
  if (!startLife) return showFormError("plan-start-error", t("plan.start.pickLife"));
  try {
    const answer = await previewStartPlan(readStartAnswers());
    drawStartSuggestion(answer);
  } catch (error) {
    showFormError("plan-start-error", error.message);
  }
}

// The suggested plan + its one-line reason; any other plan can be picked here (only at the start)
function drawStartSuggestion(answer) {
  const box = byId("plan-start-result");
  const picker = makeElement("div", "stack");
  let chosen = answer.plan_id;
  const buttons = planState.plans.map((plan) => {
    const button = makeElement("button", "choice plan-choice");
    button.type = "button";
    button.append(makeElement("span", "item-name", planName(plan.id)), makeElement("span", "item-sub", planAimText(plan)));
    button.classList.toggle("active", plan.id === chosen);
    button.addEventListener("click", () => {
      chosen = plan.id;
      buttons.forEach((b, i) => b.classList.toggle("active", planState.plans[i].id === chosen));
    });
    return button;
  });
  picker.append(...buttons);
  box.replaceChildren(
    makeTextElement("p", "plan-name", "plan.start.suggested", { plan: planName(answer.plan_id) }),
    makeTextElement("p", "muted", "plan.start." + answer.reason),
    makeTextElement("p", "small-title", "plan.start.orPick"),
    picker,
    planButton("btn", "plan.start.confirm", () => confirmStartPlan(chosen)));
  byId("plan-start-form").hidden = true;
  box.hidden = false;
}

async function confirmStartPlan(planId) {
  try {
    await startPlan({ ...readStartAnswers(), plan_id: planId });
    closeSheet("sheet-plan-start");
    loadMoneyTab(); // redraws this card + the Needs / Wants / Savings bar (it now aims at the new plan)
  } catch (error) {
    showToast(error.message, true);
  }
}

// ===== CHANGE PLAN =====
function openPlanChange() {
  looserStep = null;
  drawPlanChange();
  openSheet("sheet-plan-change");
}

function drawPlanChange() {
  const body = byId("plan-change-body");
  const items = [makeTextElement("p", "muted", "plan.change.rules", { date: firstOfMonth(planState.next_month) }),
    makeTextElement("p", "muted small", planState.changed_this_month ? "plan.change.lastChangedWait" : "plan.change.lastChanged",
      { date: formatShortDate(planState.style_changed_at.slice(0, 10)), next: firstOfMonth(planState.next_month) })];
  if (planState.changed_this_month) {
    items.push(makeTextElement("p", "warning-box", planState.pending ? "plan.change.pendingLimit" : "plan.change.limit"));
    if (planState.pending) items.push(drawPendingLine());
    body.replaceChildren(...items);
    return;
  }
  planState.plans.forEach((plan) => {
    const button = makeElement("button", "item plan-option");
    button.type = "button";
    button.disabled = plan.compared === "current";
    const left = makeElement("span");
    left.append(makeElement("span", "item-name", planName(plan.id)), makeElement("span", "item-sub", planAimText(plan)));
    button.append(left, makeTextElement("span", "tag plan-tag-" + plan.compared, "plan.compared." + plan.compared));
    button.addEventListener("click", () => choosePlan(plan));
    items.push(button);
  });
  body.replaceChildren(...items);
}

function choosePlan(plan) {
  if (plan.compared === "looser") return showLooserCost(plan.id);
  const box = makeElement("div", "stack");
  box.append(makeTextElement("p", "", "plan.change.confirmStricter", { plan: planName(plan.id) }));
  box.append(planButton("btn", "plan.change.startNext", () => sendPlanChange({ plan_id: plan.id }),
    { date: firstOfMonth(planState.next_month) }));
  if (plan.compared === "stricter") {
    box.append(planButton("btn btn-light", "plan.change.startNow", () => sendPlanChange({ plan_id: plan.id, start_now: true })));
  }
  box.append(planButton("link-btn", "plan.change.back", drawPlanChange));
  byId("plan-change-body").replaceChildren(box);
}

// Friction for a plan that saves less: what it costs, a reason, then a second "Yes, switch" tap
async function showLooserCost(planId) {
  let cost;
  try {
    cost = await previewPlanChange(planId, getTodayText());
  } catch (error) {
    return showToast(error.message, true);
  }
  const box = makeElement("div", "stack");
  box.append(makeTextElement("p", "warning-box", "plan.looser.saveLess", { amount: formatMoney(cost.save_less) }));
  if (cost.goal) {
    const key = cost.goal.months_later === null ? "plan.looser.goalNever" : "plan.looser.goalLater";
    box.append(makeTextElement("p", "", key, { goal: cost.goal.name, n: cost.goal.months_later }));
  }
  const select = makeElement("select");
  looserStep = { planId: planId, reason: select };
  select.append(makeTextElement("option", "", "plan.reason.pick"));
  select.options[0].value = "";
  PLAN_REASONS.forEach((reason) => {
    const option = makeTextElement("option", "", "plan.reason." + reason);
    option.value = reason;
    select.append(option);
  });
  const label = makeElement("label");
  label.append(makeTextElement("span", "", "plan.reason.label"), select);
  const error = makeElement("p", "message error");
  error.setAttribute("role", "alert");
  const confirm = planButton("btn btn-danger", "plan.looser.yes", () => sendLooserChange(), { date: firstOfMonth(cost.starts) });
  confirm.hidden = true;
  const next = planButton("btn btn-light", "plan.looser.understand", () => {
    if (!select.value) {
      error.textContent = t("error.REASON_REQUIRED");
      return;
    }
    error.textContent = "";
    next.hidden = true;
    confirm.hidden = false; // the second confirm
  });
  box.append(label, error, next, confirm, planButton("link-btn", "plan.change.back", drawPlanChange));
  byId("plan-change-body").replaceChildren(box);
}

async function sendLooserChange() {
  await sendPlanChange({ plan_id: looserStep.planId, confirm_looser: true, reason: looserStep.reason.value });
}

async function sendPlanChange(change) {
  try {
    planState = await changePlan({ ...change, today: getTodayText() });
    closeSheet("sheet-plan-change");
    drawPlanCard();
    showToast(t(planState.pending ? "plan.changeScheduled" : "plan.changedNow",
      { date: planState.pending ? firstOfMonth(planState.pending.start_month) : "" }));
    loadMoneyTab(); // a plan that starts now changes this month's bar
  } catch (error) {
    showToast(error.message, true);
  }
}

// ===== WHY THIS PLAN? (reason, research, history) =====
function openPlanWhy() {
  const plan = planPlan(planState.current.plan_id);
  const items = [
    makeElement("p", "plan-name", planName(plan.id)),
    makeTextElement("p", "", "plan." + plan.id + ".desc"),
    makeTextElement("p", "", "plan." + plan.id + ".why"),
    makeTextElement("p", "tag", "plan.kind." + plan.kind),
    makeElement("p", "muted small", plan.source),
    makeTextElement("p", "small-title", "plan.why.commitTitle"),
    makeTextElement("p", "muted", "plan.why.commit"),
    makeTextElement("p", "small-title", "plan.why.research"),
  ];
  planState.references.forEach((ref) => {
    const line = makeElement("p", "small");
    line.append(makeTextElement("span", "tag", "plan.kind." + ref.kind), document.createTextNode(" " + ref.text));
    items.push(line);
  });
  items.push(makeTextElement("p", "small-title", "plan.history.title"));
  (planState.history || []).forEach((period) => {
    const range = formatMonthName(period.start_month) + " – " +
      (period.end_month ? formatMonthName(period.end_month) : t("plan.history.now"));
    items.push(makeElement("p", "small", range + " · " + planName(period.plan_id) + " · " + t("plan.reason." + period.reason)));
  });
  items.push(makeTextElement("p", "small-title", "plan.history.results"));
  if (!(planState.results || []).length) items.push(makeTextElement("p", "muted small", "plan.history.noResults"));
  (planState.results || []).forEach((result) => {
    const over = result.needs_over + result.wants_over + result.savings_short;
    const text = result.status === "on_plan" ? t("plan.history.onPlan")
      : result.status === "no_data" ? t("plan.history.noData") : t("plan.history.over", { amount: formatMoney(over) });
    items.push(makeElement("p", "small", formatMonthName(result.month) + " · " + planName(result.plan_id) + " · " + text));
  });
  byId("plan-why-body").replaceChildren(...items);
  openSheet("sheet-plan-why");
}

// ===== START =====
function setUpBudgetPlan() {
  byId("plan-why-btn").addEventListener("click", openPlanWhy);
  byId("plan-start-form").addEventListener("submit", suggestStartPlan);
  document.querySelectorAll("[data-life]").forEach((button) => {
    button.addEventListener("click", () => {
      startLife = button.dataset.life;
      document.querySelectorAll("[data-life]").forEach((b) => b.classList.toggle("active", b === button));
    });
  });
  window.addEventListener("i18n:change", () => { if (planState) drawPlanCard(); }); // redraw built texts
}

setUpBudgetPlan(); // the card itself is loaded by loadMoneyTab (money-tab.js)
