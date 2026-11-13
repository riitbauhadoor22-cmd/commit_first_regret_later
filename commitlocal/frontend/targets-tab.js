// targets-tab.js — the Targets tab: money saved in the bank (with a bar split into safety net + goals),
// the monthly saving target, the safety net, and the goals list with On track / Needs more.
// It also runs the pop-ups: update bank balance, change target, new/edit goal, add money.
// All the maths (needs per month, status, warning) comes from the backend (/api/savings and /api/goals).
// Texts come from i18n.js: t("key"). The backend's status / labels are English values, translated here for display.

// ===== STATE =====
let savingsInfo = null;    // last answer from /api/savings
let goalsInfo = null;      // last answer from /api/goals
let editingGoalId = null;  // null = new goal
let chosenPriority = 2;
let moneyTarget = null;    // where "Add money" goes: { goalId: 3 } or { goalId: null } for the safety net

// Bar colours (lighter colours, so they show up on the dark card). Goals take turns using them.
const SAFETY_NET_COLOUR = "#38D6FF"; // cyan, matches the dark blue theme
const GOAL_COLOURS = ["#6FD38A", "#F5C451", "#E58FD6", "#5FD4E0", "#C5A3FF"];
const FREE_COLOUR = "#2A3655";

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
  byId("bank-balance").textContent = formatMoney(balance);
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
  if (balance === 0) {
    legend.append(makeElement("span", "", t("targets.bankEmpty")));
  }
}

// ===== 2. MONTHLY SAVING =====
function drawMonthlySaving(savings) {
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
  if (info.goals.length === 0) {
    const empty = makeElement("section", "card");
    empty.append(makeElement("p", "empty", t("targets.noGoals")));
    list.append(empty);
    return;
  }
  info.goals.forEach((goal) => list.append(makeGoalCard(goal)));
}

const STATUS_CLASSES = { "On track": "on-track", "Needs more": "needs-more", Done: "done" };
const STATUS_KEYS = { "On track": "goal.onTrack", "Needs more": "goal.needsMore", Done: "goal.done" };
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
  byId("bank-amount").value = savingsInfo ? savingsInfo.bank_balance : "";
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
  byId("target-input").value = savingsInfo.monthly_target;
  setText(byId("target-default-btn"), "targets.useDefaultAmount", { amount: formatMoney(savingsInfo.default_target) });
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
function openGoalSheet(goal) {
  editingGoalId = goal ? goal.id : null;
  setText(byId("goal-title"), goal ? "goal.edit" : "goal.new");
  byId("goal-delete").hidden = !goal;
  byId("goal-error").textContent = "";
  byId("goal-name").value = goal ? goal.name : "";
  byId("goal-target").value = goal ? goal.target_amount : "";
  byId("goal-deadline").value = goal ? goal.deadline : "";
  pickPriority(goal ? goal.priority : 2);
  openSheet("sheet-goal");
  if (!goal) byId("goal-name").focus();
}

function readGoalForm() {
  return {
    name: byId("goal-name").value.trim(),
    target_amount: Number(byId("goal-target").value),
    deadline: byId("goal-deadline").value,
    priority: chosenPriority,
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
  document.querySelectorAll("[data-priority]").forEach((button) => {
    button.addEventListener("click", () => pickPriority(Number(button.dataset.priority)));
  });
}
