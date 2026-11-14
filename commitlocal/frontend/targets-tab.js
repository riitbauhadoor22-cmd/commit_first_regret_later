// targets-tab.js — the Targets tab: money saved in the bank (with a bar split into safety net + goals),
// the monthly saving target, the safety net, and the goals list with On track / Needs more.
// It also runs the pop-ups: update bank balance, change target, new/edit goal, add money.
// All the maths (needs per month, status, warning, inflation estimate) comes from the backend
// (/api/savings, /api/goals and the Statistics Mauritius CPI projection).
// Texts come from i18n.js: t("key"). The backend's status / labels are English values, translated here for display.

// ===== STATE =====
let savingsInfo = null;    // last answer from /api/savings
let goalsInfo = null;      // last answer from /api/goals
let editingGoalId = null;  // null = new goal
let chosenPriority = 2;
let editingGoalSaved = 0;  // money already in the goal being edited (for the inflation preview)
let previewTimer = null;   // waits a moment after typing before asking for the inflation preview
let previewNumber = 0;     // only the newest preview answer is shown
let moneyTarget = null;    // where "Add money" goes: { goalId: 3 } or { goalId: null } for the safety net

// Bar colours (lighter colours, so they show up on the dark card). Goals take turns using them.
const SAFETY_NET_COLOUR = "#38D6FF"; // cyan, matches the dark blue theme
const GOAL_COLOURS = ["#6FD38A", "#F5C451", "#E58FD6", "#5FD4E0", "#C5A3FF"];
const FREE_COLOUR = "#2A3655";

// Goal categories (same list as backend/categories.py GOAL_CPI_CATEGORIES) → text keys
const GOAL_CATEGORY_KEYS = {
  Phone: "goalCat.phone", Laptop: "goalCat.laptop", Electronics: "goalCat.electronics",
  Games: "goalCat.games", Hobbies: "goalCat.hobbies", Concerts: "goalCat.concerts",
  Clothes: "goalCat.clothes", Shoes: "goalCat.shoes",
  Travel: "goalCat.travel", Car: "goalCat.car", Transport: "goalCat.transport",
  Course: "goalCat.course", Books: "goalCat.books", Food: "goalCat.food", Groceries: "goalCat.groceries",
  Events: "goalCat.events", "Eating out": "goalCat.eatingOut", Holidays: "goalCat.holidays",
  Furniture: "goalCat.furniture", Appliances: "goalCat.appliances", Health: "goalCat.health", Gym: "goalCat.gym",
  Other: "goalCat.other",
};
// CPI categories the backend can answer with (English names from data/cpi_mauritius.csv) → text keys
const CPI_CATEGORY_KEYS = {
  "All Items": "cpi.allItems",
  "Information and communication": "cpi.communication",
  "Recreation, sports and culture": "cpi.recreation",
  "Clothing and footwear": "cpi.clothing",
  Transport: "cpi.transport",
  "Education services": "cpi.education",
  "Food and non-alcoholic beverages": "cpi.food",
  "Restaurants and accommodation services": "cpi.restaurants",
  "Furnishings, household equipment and routine household maintenance": "cpi.furnishings",
  Health: "cpi.health",
};
const INFLATION_REASON_KEYS = {
  DATA_UNAVAILABLE: "inflation.unavailable", DEADLINE_PASSED: "inflation.deadlinePassed",
  DEADLINE_TOO_SOON: "inflation.tooSoon",
};
const INFLATION_WARNING_KEYS = {
  LONG_HORIZON: "inflation.longHorizon", FALLBACK_ALL_ITEMS: "inflation.fallback",
  FUNDED_BUT_SHORT: "inflation.fundedShort",
};

// ===== LOAD AND DRAW =====
async function loadTargetsTab() {
  try {
    const [savings, goals] = await Promise.all([getSavings(), getGoals()]);
    savingsInfo = savings;
    goalsInfo = goals;
    drawBankCard(savings.bank_balance, savings.bank_bar);
    drawMonthlySaving(savings);
    drawSafetyNet(savings.safety_net);
    drawGoals(goals);
  } catch (error) {
    showToast(error.message, true);
  }
}

// "2027-03-01" -> "1 Mar 2027" / "1 mars 2027"
function formatLongDate(dateText) {
  const [year, month, day] = dateText.split("-").map(Number);
  return I18n.formatDate(new Date(year, month - 1, day), { day: "numeric", month: "short", year: "numeric" });
}

// Bank bar part name: "Safety net" / "Free" come from the backend in English, goal names are the user's own
function getPartName(part) {
  if (part.goal_id !== null) return part.label;
  return part.label === "Free" ? t("targets.free") : t("targets.safetyNet");
}

// The colour of each part of the bank bar: safety net, then one per goal, then "Free"
function getPartColour(part, goalNumber) {
  if (part.label === "Free" && part.goal_id === null) return FREE_COLOUR;
  if (part.goal_id === null) return SAFETY_NET_COLOUR;
  return GOAL_COLOURS[goalNumber % GOAL_COLOURS.length];
}

// goal id -> colour, so each goal card shows the same colour as its part of the bar
let goalColours = {};

// ===== 1. DARK CARD: SAVED IN YOUR BANK =====
function drawBankCard(balance, parts) {
  // null = the user hasn't added a bank balance: say so, don't show Rs 0
  byId("bank-balance").textContent = balance === null ? t("targets.notAdded") : formatMoney(balance);
  const bar = byId("bank-bar");
  const legend = byId("bank-legend");
  bar.replaceChildren();
  legend.replaceChildren();
  goalColours = {};

  let goalNumber = 0;
  parts.forEach((part) => {
    const colour = getPartColour(part, goalNumber);
    if (part.goal_id !== null) {
      goalColours[part.goal_id] = colour;
      goalNumber += 1;
    }
    const piece = makeElement("span");
    piece.style.width = part.percent + "%";
    piece.style.background = colour;
    bar.append(piece);

    if (part.amount > 0) {
      const item = makeElement("span");
      const dot = makeElement("span", "dot");
      dot.style.background = colour;
      item.append(dot, getPartName(part) + " " + formatMoney(part.amount));
      legend.append(item);
    }
  });
  if (balance === null) {
    legend.append(makeElement("span", "", t("targets.bankNotAdded")));
  } else if (balance === 0) {
    legend.append(makeElement("span", "", t("targets.bankEmpty")));
  }
}

// ===== 2. MONTHLY SAVING =====
function drawMonthlySaving(savings) {
  if (savings.monthly_target === null) { // no own target and no regular income: no made-up target
    byId("target-amount").textContent = "—";
    byId("target-note").textContent = t("targets.noTargetNote");
    byId("target-bar").style.width = "0%";
    byId("target-progress").textContent = savings.saved_this_month > 0
      ? t("targets.savedThisMonth", { amount: formatMoney(savings.saved_this_month) }) : "";
    return;
  }
  byId("target-amount").textContent = t("common.perMonth", { amount: formatMoney(savings.monthly_target) });
  byId("target-note").textContent = savings.monthly_target_custom === null
    ? t("targets.defaultNote")
    : t("targets.ownTarget");
  const percent = savings.monthly_target > 0 ? Math.min(savings.saved_this_month / savings.monthly_target * 100, 100) : 0;
  byId("target-bar").style.width = percent + "%";
  byId("target-progress").textContent =
    t("targets.progress", { a: formatMoney(savings.saved_this_month), b: formatMoney(savings.monthly_target) });
}

// ===== 3. SAFETY NET =====
function drawSafetyNet(net) {
  byId("safety-bar").style.width = net.percent + "%";
  if (net.target === 0) {
    byId("safety-text").textContent =
      t("targets.safetyNoBills");
    byId("safety-percent").textContent = net.saved > 0 ? t("targets.saved", { amount: formatMoney(net.saved) }) : "";
    return;
  }
  byId("safety-text").textContent =
    t("targets.safetyOf", { a: formatMoney(net.saved), b: formatMoney(net.target) });
  byId("safety-percent").textContent = t("targets.reached", { n: Math.round(net.percent) });
}

// ===== 4 + 5. GOALS LIST AND WARNING =====
function drawGoals(info) {
  const warning = byId("goals-warning");
  warning.hidden = !info.warning;
  // Built here from the numbers (the backend's warning text is English only)
  warning.textContent = info.warning
    ? "⚠ " + t("targets.goalsWarning", { need: formatMoney(info.total_needed), save: formatMoney(info.monthly_target) })
    : "";

  const list = byId("goal-list");
  list.replaceChildren();
  const prompted = drawSavingsPrompt(info.goals.length);
  if (info.goals.length === 0 && !prompted) {
    const empty = makeElement("section", "card");
    empty.append(makeElement("p", "empty", t("targets.noGoalsPrompt")));
    list.append(empty);
  }
  if (info.goals.length === 0) return;
  info.goals.forEach((goal) => list.append(makeGoalCard(goal)));
}

// "I'm not saving right now" (or Undo) — only while there are no goals and no savings records.
// Returns true when it drew something (then the plain "no goals" card isn't needed).
function drawSavingsPrompt(goalCount) {
  const box = byId("savings-prompt");
  box.replaceChildren();
  const state = savingsInfo ? savingsInfo.info : "provided";
  if (goalCount > 0 || state === "provided") return false;
  const texts = { ask: "targets.prompt.savings", add: "targets.newGoalButton", none: "targets.none.savings",
    marked: "targets.marked.savings" };
  const prompt = makeInfoPrompt("savings", state, texts, "", () => openGoalSheet(null), loadTargetsTab);
  if (!prompt) return false;
  const card = makeElement("section", "card");
  card.append(prompt);
  box.append(card);
  return true;
}

// "No target" = no saving target is known yet, so we can't say if a goal is on track (no guess)
const STATUS_CLASSES = { "On track": "on-track", "Needs more": "needs-more", Done: "done", "No target": "no-target" };
const STATUS_KEYS = { "On track": "goal.onTrack", "Needs more": "goal.needsMore", Done: "goal.done",
  "No target": "goal.noTarget" };
const PRIORITY_KEYS = { 1: "goal.priorityHigh", 2: "goal.priorityMedium", 3: "goal.priorityLow" };

function makeGoalCard(goal) {
  const card = makeElement("section", "card goal-card");

  // Name + status tag
  const top = makeElement("div", "goal-top");
  const title = makeElement("h3");
  const dot = makeElement("span", "dot");
  dot.style.background = goalColours[goal.id] || GOAL_COLOURS[0];
  title.append(dot, goal.name);
  top.append(title, makeElement("span", "status " + STATUS_CLASSES[goal.status], t(STATUS_KEYS[goal.status]) || goal.status));
  card.append(top);

  // Deadline + priority
  const meta = makeElement("div", "goal-meta");
  meta.append(makeElement("span", "muted", t("goal.by", { date: formatLongDate(goal.deadline) }) + " ·"));
  meta.append(makeElement("span", "tag", t(PRIORITY_KEYS[goal.priority]) || goal.priority_name));
  card.append(meta);

  // Progress bar
  const bar = makeElement("div", "bar");
  const fill = makeElement("span");
  fill.style.width = goal.percent + "%";
  bar.append(fill);
  card.append(bar);

  // "Rs 4,500 of Rs 15,000"   "Needs Rs 2,100 a month"
  const numbers = makeElement("div", "goal-numbers");
  const saved = makeElement("span");
  saved.append(makeElement("strong", "", formatMoney(goal.saved_amount)), " " + t("common.of") + " " + formatMoney(goal.target_amount));
  numbers.append(saved);
  if (goal.status !== "Done") {
    numbers.append(makeElement("span", "muted", t("goal.needsPerMonth", { amount: formatMoney(goal.needs_per_month) })));
  }
  card.append(numbers);

  // Inflation estimate (filled in when the backend answers; stays hidden if it can't)
  const inflationBox = makeElement("div", "inflation-box");
  inflationBox.hidden = true;
  card.append(inflationBox);
  getGoalInflation(goal.id).then((p) => drawInflation(inflationBox, p, goal.deadline)).catch(() => {});

  // Edit + Add money
  const actions = makeElement("div", "goal-actions");
  const editButton = makeElement("button", "link-btn", t("common.edit"));
  editButton.type = "button";
  editButton.setAttribute("aria-label", t("goal.editAria", { name: goal.name }));
  editButton.addEventListener("click", () => openGoalSheet(goal));
  actions.append(editButton);
  if (goal.status !== "Done") {
    const addButton = makeElement("button", "btn btn-small btn-light", t("targets.addMoneyButton"));
    addButton.type = "button";
    addButton.setAttribute("aria-label", t("goal.addMoneyAria", { name: goal.name }));
    addButton.addEventListener("click", () => openMoneySheet(goal));
    actions.append(addButton);
  }
  card.append(actions);
  return card;
}

// ===== POP-UP: BANK BALANCE =====
function openBankSheet() {
  byId("bank-amount").value = savingsInfo && savingsInfo.bank_balance !== null ? savingsInfo.bank_balance : "";
  byId("bank-error").textContent = "";
  openSheet("sheet-bank");
  byId("bank-amount").focus();
}

async function saveBankForm(event) {
  event.preventDefault();
  const text = byId("bank-amount").value;
  const balance = Number(text);
  if (text === "" || !(balance >= 0)) {
    showFormError("bank-error", t("form.zeroOrMore"));
    return;
  }
  await saveSavings(balance, savingsInfo.monthly_target_custom, "sheet-bank", "bank-error", t("toast.bankSaved"));
}

// ===== POP-UP: MONTHLY SAVING TARGET =====
function openTargetSheet() {
  byId("target-input").value = savingsInfo.monthly_target === null ? "" : savingsInfo.monthly_target;
  byId("target-default-btn").hidden = savingsInfo.default_target === null; // no income → no 20% default to offer
  if (savingsInfo.default_target !== null) {
    setText(byId("target-default-btn"), "targets.useDefaultAmount", { amount: formatMoney(savingsInfo.default_target) });
  }
  byId("target-error").textContent = "";
  openSheet("sheet-target");
  byId("target-input").focus();
}

async function saveTargetForm(event) {
  event.preventDefault();
  const text = byId("target-input").value;
  const target = Number(text);
  if (text === "" || !(target >= 0)) {
    showFormError("target-error", t("form.zeroOrMore"));
    return;
  }
  await saveSavings(savingsInfo.bank_balance, target, "sheet-target", "target-error", t("toast.targetSaved"));
}

async function useDefaultTarget() {
  // An empty target tells the backend to use 20% of regular income again
  await saveSavings(savingsInfo.bank_balance, null, "sheet-target", "target-error", t("toast.usingDefault"));
}

async function saveSavings(balance, target, sheetId, errorId, doneMessage) {
  try {
    await updateSavings(balance, target);
    showToast(doneMessage);
    closeSheet(sheetId);
    await loadTargetsTab();
  } catch (error) {
    showFormError(errorId, error.message);
  }
}

// ===== POP-UP: NEW / EDIT GOAL =====
function pickPriority(priority) {
  chosenPriority = priority;
  document.querySelectorAll("[data-priority]").forEach((button) => {
    const isChosen = Number(button.dataset.priority) === priority;
    button.classList.toggle("active", isChosen);
    button.setAttribute("aria-pressed", isChosen);
  });
}

// goal = null → empty "New goal" form
// ===== INFLATION ESTIMATE (Statistics Mauritius CPI) =====
// "2026-10" → "Oct 2026" in the chosen language
function formatMonth(monthText) {
  const [year, month] = monthText.split("-").map(Number);
  return I18n.formatDate(new Date(year, month - 1, 1), { month: "short", year: "numeric" });
}

// Fills `box` with the backend's projection p (or a short message when there is none)
function drawInflation(box, p, deadline) {
  box.replaceChildren();
  box.hidden = false;
  if (!p.available) {
    box.append(makeElement("p", "muted", t(INFLATION_REASON_KEYS[p.reason] || "inflation.unavailable")));
    return;
  }
  // "Estimated cost by 1 Sep 2027: Rs 31,900 (+Rs 1,900 due to inflation)"
  const extra = p.extra_needed;
  const change = extra > 0 ? t("inflation.more", { amount: formatMoney(extra) })
    : extra < 0 ? t("inflation.less", { amount: formatMoney(-extra) }) : t("inflation.same");
  const cost = makeElement("p");
  cost.append(t("inflation.costBy", { date: formatLongDate(deadline) }) + " ",
    makeElement("strong", "", formatMoney(p.projected_cost)), " " + change);
  box.append(cost);
  if (p.monthly_saving_adjusted > 0) {
    box.append(makeElement("p", "", t("inflation.saveInstead", {
      a: formatMoney(p.monthly_saving_adjusted), b: formatMoney(p.monthly_saving_original) })));
  }
  p.warnings.forEach((w) => {
    const key = INFLATION_WARNING_KEYS[w.code];
    if (key) box.append(makeElement("p", "inflation-warn", "⚠ " + t(key, { amount: formatMoney(Math.max(extra, 0)) })));
  });
  // Small grey source line: rate, category, data month, "estimate only"
  box.append(makeElement("p", "fine-print", t("inflation.basedOn", {
    category: t(CPI_CATEGORY_KEYS[p.category_used]) || p.category_used,
    rate: p.inflation_rate_used.toFixed(1),
    month: formatMonth(p.data_as_of),
  })));
}

// The goal form's "What is it for?" list (rebuilt each time so it follows the language)
function fillGoalCategories(chosen) {
  const select = byId("goal-category");
  const makeChoice = (text, value) => {
    const choice = makeElement("option", "", text);
    choice.value = value;
    return choice;
  };
  select.replaceChildren(makeChoice(t("goal.categoryPick"), ""));
  Object.entries(GOAL_CATEGORY_KEYS).forEach(([value, key]) => select.append(makeChoice(t(key), value)));
  select.value = chosen || "";
}

// Live preview: waits 400 ms after the last change, then asks the backend
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(showInflationPreview, 400);
}

async function showInflationPreview() {
  const box = byId("goal-inflation-preview");
  const goal = readGoalForm();
  if (!(goal.target_amount > 0) || !goal.deadline || !goal.category) {
    box.hidden = true;
    return;
  }
  const number = ++previewNumber;
  try {
    const p = await getInflationPreview({ target: goal.target_amount, current: editingGoalSaved,
                                          deadline: goal.deadline, category: goal.category });
    if (number === previewNumber) drawInflation(box, p, goal.deadline);
  } catch (error) {
    if (number === previewNumber) box.hidden = true; // offline etc.: just no preview
  }
}

function openGoalSheet(goal) {
  editingGoalId = goal ? goal.id : null;
  editingGoalSaved = goal ? goal.saved_amount : 0;
  setText(byId("goal-title"), goal ? "goal.edit" : "goal.new");
  byId("goal-delete").hidden = !goal;
  byId("goal-error").textContent = "";
  byId("goal-name").value = goal ? goal.name : "";
  byId("goal-target").value = goal ? goal.target_amount : "";
  byId("goal-deadline").value = goal ? goal.deadline : "";
  pickPriority(goal ? goal.priority : 2);
  fillGoalCategories(goal ? goal.category : "");
  byId("goal-inflation-preview").hidden = true;
  showInflationPreview();
  openSheet("sheet-goal");
  if (!goal) byId("goal-name").focus();
}

function readGoalForm() {
  return {
    name: byId("goal-name").value.trim(),
    target_amount: Number(byId("goal-target").value),
    deadline: byId("goal-deadline").value,
    priority: chosenPriority,
    category: byId("goal-category").value || null,
  };
}

// Quick checks so the user gets an answer straight away (the backend checks again)
function findGoalProblem(goal) {
  if (!goal.name) return t("form.goalName");
  if (!(goal.target_amount > 0)) return t("form.targetAbove0");
  if (!goal.deadline) return t("form.pickDeadline");
  return "";
}

async function saveGoalForm(event) {
  event.preventDefault();
  const goal = readGoalForm();
  const problem = findGoalProblem(goal);
  if (problem) {
    showFormError("goal-error", problem);
    return;
  }
  const saveButton = byId("goal-save");
  saveButton.disabled = true;
  try {
    if (editingGoalId === null) {
      await addGoal(goal);
      showToast(t("toast.goalAdded"));
    } else {
      await editGoal(editingGoalId, goal);
      showToast(t("toast.goalUpdated"));
    }
    closeSheet("sheet-goal");
    await loadTargetsTab();
  } catch (error) {
    showFormError("goal-error", error.message);
  } finally {
    saveButton.disabled = false;
  }
}

async function deleteShownGoal() {
  if (!confirm(t("confirm.deleteGoal"))) return;
  try {
    await deleteGoal(editingGoalId);
    showToast(t("toast.goalDeleted"));
    closeSheet("sheet-goal");
    await loadTargetsTab();
  } catch (error) {
    showFormError("goal-error", error.message);
  }
}

// ===== POP-UP: ADD MONEY (goal = null → safety net) =====
function openMoneySheet(goal) {
  moneyTarget = { goalId: goal ? goal.id : null };
  if (goal) setText(byId("money-title"), "targets.addMoneyTo", { name: goal.name });
  else setText(byId("money-title"), "targets.addMoneySafety");
  if (goal) setText(byId("money-hint"), "targets.stillNeeded", { amount: formatMoney(goal.target_amount - goal.saved_amount) });
  else setText(byId("money-hint"), "targets.alsoBank");
  byId("money-amount").value = "";
  byId("money-error").textContent = "";
  openSheet("sheet-money");
  byId("money-amount").focus();
}

async function saveMoneyForm(event) {
  event.preventDefault();
  const amount = Number(byId("money-amount").value);
  if (!(amount > 0)) {
    showFormError("money-error", t("form.amountAbove0"));
    return;
  }
  const saveButton = byId("money-save");
  saveButton.disabled = true;
  try {
    if (moneyTarget.goalId === null) {
      await addToSafetyNet(amount);
      showToast(t("toast.addedSafety", { amount: formatMoney(amount) }));
    } else {
      const result = await addMoneyToGoal(moneyTarget.goalId, amount);
      // The backend never fills a goal past its target, so it may have added less
      const message = result.added < amount
        ? t("toast.addedGoalFull", { amount: formatMoney(result.added) })
        : t("toast.added", { name: formatMoney(result.added) });
      showToast(message);
    }
    closeSheet("sheet-money");
    await loadTargetsTab();
  } catch (error) {
    showFormError("money-error", error.message);
  } finally {
    saveButton.disabled = false;
  }
}

// ===== START (called by app.js once you're logged in) =====
function startTargetsTab() {
  byId("bank-edit-btn").addEventListener("click", openBankSheet);
  byId("target-edit-btn").addEventListener("click", openTargetSheet);
  byId("safety-add-btn").addEventListener("click", () => openMoneySheet(null));
  byId("new-goal-btn").addEventListener("click", () => openGoalSheet(null));

  byId("bank-form").addEventListener("submit", saveBankForm);
  byId("target-form").addEventListener("submit", saveTargetForm);
  byId("target-default-btn").addEventListener("click", useDefaultTarget);
  byId("goal-form").addEventListener("submit", saveGoalForm);
  byId("goal-delete").addEventListener("click", deleteShownGoal);
  byId("money-form").addEventListener("submit", saveMoneyForm);
  ["goal-target", "goal-deadline", "goal-category"].forEach((id) => {
    byId(id).addEventListener("input", schedulePreview);
    byId(id).addEventListener("change", schedulePreview);
  });
  document.querySelectorAll("[data-priority]").forEach((button) => {
    button.addEventListener("click", () => pickPriority(Number(button.dataset.priority)));
  });
}
