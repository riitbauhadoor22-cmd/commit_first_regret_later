// targets-tab.js — the Targets tab: money saved in the bank (with a bar split into safety net + goals),
// the monthly saving target, the safety net, and the goals list with On track / Needs more.
// It also runs the pop-ups: update bank balance, change target, new/edit goal, add money.
// All the maths (needs per month, status, warning) comes from the backend (/api/savings and /api/goals).

// ===== STATE =====
let savingsInfo = null;    // last answer from /api/savings
let goalsInfo = null;      // last answer from /api/goals
let editingGoalId = null;  // null = new goal
let chosenPriority = 2;
let moneyTarget = null;    // where "Add money" goes: { goalId: 3 } or { goalId: null } for the safety net

// Bar colours (lighter colours, so they show up on the dark card). Goals take turns using them.
const SAFETY_NET_COLOUR = "#8FA6FF";
const GOAL_COLOURS = ["#6FD38A", "#F5C451", "#E58FD6", "#5FD4E0", "#C5A3FF"];
const FREE_COLOUR = "#3A3E46";

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

// "2027-03-01" -> "1 Mar 2027"
function formatLongDate(dateText) {
  const [year, month, day] = dateText.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
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
      item.append(dot, part.label + " " + formatMoney(part.amount));
      legend.append(item);
    }
  });
  if (balance === 0) {
    legend.append(makeElement("span", "", "Tap Update to type in what you have saved."));
  }
}

// ===== 2. MONTHLY SAVING =====
function drawMonthlySaving(savings) {
  byId("target-amount").textContent = formatMoney(savings.monthly_target) + " a month";
  byId("target-note").textContent = savings.monthly_target_custom === null
    ? "20% of your regular income. Tap Change to pick your own amount."
    : "Your own target.";
  const percent = savings.monthly_target > 0 ? Math.min(savings.saved_this_month / savings.monthly_target * 100, 100) : 0;
  byId("target-bar").style.width = percent + "%";
  byId("target-progress").textContent =
    formatMoney(savings.saved_this_month) + " of " + formatMoney(savings.monthly_target) + " put away this month";
}

// ===== 3. SAFETY NET =====
function drawSafetyNet(net) {
  byId("safety-bar").style.width = net.percent + "%";
  if (net.target === 0) {
    byId("safety-text").textContent =
      "Your safety net is 3 months of fixed bills. Add your bills in Money → Fixed monthly to set it.";
    byId("safety-percent").textContent = net.saved > 0 ? formatMoney(net.saved) + " saved" : "";
    return;
  }
  byId("safety-text").textContent =
    formatMoney(net.saved) + " of " + formatMoney(net.target) + " (3 × your fixed monthly bills)";
  byId("safety-percent").textContent = Math.round(net.percent) + "% reached";
}

// ===== 4 + 5. GOALS LIST AND WARNING =====
function drawGoals(info) {
  const warning = byId("goals-warning");
  warning.hidden = !info.warning;
  warning.textContent = info.warning ? "⚠ " + info.warning : "";

  const list = byId("goal-list");
  list.replaceChildren();
  if (info.goals.length === 0) {
    const empty = makeElement("section", "card");
    empty.append(makeElement("p", "empty", "No goals yet. Tap “+ New goal” to save for a phone, a trip or anything else."));
    list.append(empty);
    return;
  }
  info.goals.forEach((goal) => list.append(makeGoalCard(goal)));
}

const STATUS_CLASSES = { "On track": "on-track", "Needs more": "needs-more", Done: "done" };

function makeGoalCard(goal) {
  const card = makeElement("section", "card goal-card");

  // Name + status tag
  const top = makeElement("div", "goal-top");
  const title = makeElement("h3");
  const dot = makeElement("span", "dot");
  dot.style.background = goalColours[goal.id] || GOAL_COLOURS[0];
  title.append(dot, goal.name);
  top.append(title, makeElement("span", "status " + STATUS_CLASSES[goal.status], goal.status));
  card.append(top);

  // Deadline + priority
  const meta = makeElement("div", "goal-meta");
  meta.append(makeElement("span", "muted", "By " + formatLongDate(goal.deadline) + " ·"));
  meta.append(makeElement("span", "tag", goal.priority_name + " priority"));
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
  saved.append(makeElement("strong", "", formatMoney(goal.saved_amount)), " of " + formatMoney(goal.target_amount));
  numbers.append(saved);
  if (goal.status !== "Done") {
    numbers.append(makeElement("span", "muted", "Needs " + formatMoney(goal.needs_per_month) + " a month"));
  }
  card.append(numbers);

  // Edit + Add money
  const actions = makeElement("div", "goal-actions");
  const editButton = makeElement("button", "link-btn", "Edit");
  editButton.type = "button";
  editButton.setAttribute("aria-label", "Edit " + goal.name);
  editButton.addEventListener("click", () => openGoalSheet(goal));
  actions.append(editButton);
  if (goal.status !== "Done") {
    const addButton = makeElement("button", "btn btn-small btn-light", "+ Add money");
    addButton.type = "button";
    addButton.setAttribute("aria-label", "Add money to " + goal.name);
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
    showFormError("bank-error", "Please enter 0 or more.");
    return;
  }
  await saveSavings(balance, savingsInfo.monthly_target_custom, "sheet-bank", "bank-error", "Bank balance saved");
}

// ===== POP-UP: MONTHLY SAVING TARGET =====
function openTargetSheet() {
  byId("target-input").value = savingsInfo.monthly_target;
  byId("target-default-btn").textContent =
    "Use 20% of my regular income (" + formatMoney(savingsInfo.default_target) + ")";
  byId("target-error").textContent = "";
  openSheet("sheet-target");
  byId("target-input").focus();
}

async function saveTargetForm(event) {
  event.preventDefault();
  const text = byId("target-input").value;
  const target = Number(text);
  if (text === "" || !(target >= 0)) {
    showFormError("target-error", "Please enter 0 or more.");
    return;
  }
  await saveSavings(savingsInfo.bank_balance, target, "sheet-target", "target-error", "Target saved");
}

async function useDefaultTarget() {
  // An empty target tells the backend to use 20% of regular income again
  await saveSavings(savingsInfo.bank_balance, null, "sheet-target", "target-error", "Using 20% of your regular income");
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
  byId("goal-title").textContent = goal ? "Edit goal" : "New goal";
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
  if (!goal.name) return "Please give the goal a name.";
  if (!(goal.target_amount > 0)) return "Please enter a target above 0.";
  if (!goal.deadline) return "Please pick a deadline.";
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
      showToast("Goal added");
    } else {
      await editGoal(editingGoalId, goal);
      showToast("Goal updated");
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
  if (!confirm("Delete this goal? The money you saved for it stays in your bank balance.")) return;
  try {
    await deleteGoal(editingGoalId);
    showToast("Goal deleted");
    closeSheet("sheet-goal");
    await loadTargetsTab();
  } catch (error) {
    showFormError("goal-error", error.message);
  }
}

// ===== POP-UP: ADD MONEY (goal = null → safety net) =====
function openMoneySheet(goal) {
  moneyTarget = { goalId: goal ? goal.id : null };
  byId("money-title").textContent = goal ? "Add money: " + goal.name : "Add money: Safety net";
  byId("money-hint").textContent = goal
    ? "Still needed: " + formatMoney(goal.target_amount - goal.saved_amount) + ". It's also added to your bank balance."
    : "It's also added to your bank balance.";
  byId("money-amount").value = "";
  byId("money-error").textContent = "";
  openSheet("sheet-money");
  byId("money-amount").focus();
}

async function saveMoneyForm(event) {
  event.preventDefault();
  const amount = Number(byId("money-amount").value);
  if (!(amount > 0)) {
    showFormError("money-error", "Please enter an amount above 0.");
    return;
  }
  const saveButton = byId("money-save");
  saveButton.disabled = true;
  try {
    if (moneyTarget.goalId === null) {
      await addToSafetyNet(amount);
      showToast("Added " + formatMoney(amount) + " to your safety net");
    } else {
      const result = await addMoneyToGoal(moneyTarget.goalId, amount);
      // The backend never fills a goal past its target, so it may have added less
      const message = result.added < amount
        ? "Added " + formatMoney(result.added) + ". That's all this goal needed!"
        : "Added " + formatMoney(result.added);
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
