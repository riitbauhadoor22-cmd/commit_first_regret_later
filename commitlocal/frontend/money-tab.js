// money-tab.js — the Money tab: month picker, dark summary card, Money in / Money out switch,
// Money out (quick-add chips, category budgets, fixed bills, recent expenses), Money in (regular and
// one-off income), and the Add expense, Add income and Set budget pop-ups. All the maths comes from the backend (/api/summary).

// ===== STATE (what the tab is showing right now) =====
let shownMonth = getThisMonthText();
let categoryList = [];      // [{category, default_kind, spent, budget, ...}] from the last summary
let editingExpenseId = null; // null = adding a new expense
let chosenCategory = null;
let chosenKind = null;
let budgetCategory = null;  // which category the budget pop-up is for
let incomeTypes = [];       // ["Salary", "Allowance", ...] from the backend
let editingIncomeId = null; // null = adding new income
let chosenIncomeType = null;
let chosenFrequency = null;

// ===== LOAD AND DRAW THE WHOLE TAB =====
async function loadMoneyTab() {
  byId("month-label").textContent = formatMonthName(shownMonth);
  try {
    const [summary, chips, income] = await Promise.all([getSummary(shownMonth), getQuickAdd(), getIncome(shownMonth)]);
    categoryList = summary.categories;
    incomeTypes = income.types;
    drawSummaryCard(summary);
    drawQuickAdd(chips);
    drawCategoryRows(summary.categories);
    drawFixedBills(summary.fixed_bills, summary.fixed_total);
    drawRecent(summary.recent);
    drawIncomeLists(income.regular, income.one_off);
  } catch (error) {
    showToast(error.message, true);
  }
}

function changeMonth(count) {
  shownMonth = addMonths(shownMonth, count);
  loadMoneyTab();
}

// ===== DARK SUMMARY CARD =====
function drawSummaryCard(summary) {
  const left = byId("left-to-spend");
  left.textContent = summary.left_to_spend < 0 ? formatOut(summary.left_to_spend) : formatMoney(summary.left_to_spend);
  left.classList.toggle("negative", summary.left_to_spend < 0);

  // The 3 small numbers are rounded to whole rupees so they fit on small phones
  byId("sum-in").textContent = formatIn(Math.round(summary.income));
  byId("sum-out").textContent = formatOut(Math.round(summary.spent));
  byId("sum-saved").textContent = formatMoney(Math.round(summary.saved));

  drawSplitBar(summary.needs_percent, summary.wants_percent, summary.savings_percent);
}

// The Needs / Wants / Savings bar. If they add up to more than 100%, the bar is squeezed to fit.
function drawSplitBar(needs, wants, savings) {
  const total = Math.max(needs + wants + savings, 100);
  byId("split-needs").style.width = (needs / total) * 100 + "%";
  byId("split-wants").style.width = (wants / total) * 100 + "%";
  byId("split-savings").style.width = (savings / total) * 100 + "%";

  const legend = byId("split-legend");
  legend.replaceChildren(
    makeLegendItem("split-needs", "Needs " + Math.round(needs) + "%"),
    makeLegendItem("split-wants", "Wants " + Math.round(wants) + "%"),
    makeLegendItem("split-savings", "Savings " + Math.round(savings) + "%"),
    makeElement("span", "aim", "aim 50 · 30 · 20")
  );
}

function makeLegendItem(colourClass, text) {
  const item = makeElement("span");
  item.append(makeElement("span", "dot " + colourClass), text);
  return item;
}

// ===== QUICK ADD CHIPS =====
function drawQuickAdd(chips) {
  byId("quick-box").hidden = chips.length === 0;
  const box = byId("quick-chips");
  box.replaceChildren();
  chips.forEach((chip) => {
    const button = makeElement("button", "chip", chip.label);
    button.type = "button";
    button.setAttribute("aria-label", "Add " + chip.label + " again today");
    button.addEventListener("click", () => saveQuickExpense(chip, button));
    box.append(button);
  });
}

async function saveQuickExpense(chip, button) {
  button.disabled = true; // stops a double tap saving it twice
  try {
    await addQuickExpense(chip);
    showToast("Added " + chip.label);
    await loadMoneyTab();
  } catch (error) {
    showToast(error.message, true);
    button.disabled = false;
  }
}

// ===== CATEGORY ROWS (spent / budget + progress bar) =====
function drawCategoryRows(rows) {
  const box = byId("category-rows");
  box.replaceChildren();
  rows.forEach((row) => box.append(makeCategoryRow(row)));
}

function makeCategoryRow(row) {
  const item = makeElement("div", "cat-row");
  const top = makeElement("div", "cat-top");
  top.append(makeElement("span", "cat-name", row.category));

  // Right side: "Rs 2,300 / Rs 4,000"  or  "Rs 190  Set budget"
  const right = makeElement("span", "cat-right");
  const amount = makeElement("span", "cat-amount");
  amount.append(makeElement("strong", "", formatMoney(row.spent)));
  right.append(amount);
  top.append(right);
  item.append(top);

  if (row.budget === null) {
    right.append(makeBudgetLink("Set budget", row.category, null)); // no budget: no bar
    return item;
  }
  amount.append(" / " + formatMoney(row.budget));

  const bar = makeElement("div", row.over_by > 0 ? "bar over" : "bar");
  const fill = makeElement("span");
  fill.style.width = Math.min(row.percent, 100) + "%";
  bar.append(fill);
  item.append(bar);

  // Under the bar: the warning (if over budget) on the left, "Edit" on the right
  const bottom = makeElement("div", "cat-bottom");
  const warning = row.over_by > 0 ? "⚠ Over budget by " + formatMoney(row.over_by) : "";
  bottom.append(makeElement("p", "warn", warning), makeBudgetLink("Edit", row.category, row.budget));
  item.append(bottom);
  return item;
}

function makeBudgetLink(text, category, currentLimit) {
  const link = makeElement("button", "link-btn", text);
  link.type = "button";
  link.setAttribute("aria-label", (text === "Edit" ? "Edit budget" : text) + " for " + category);
  link.addEventListener("click", () => openBudgetSheet(category, currentLimit));
  return link;
}

// ===== FIXED MONTHLY BILLS =====
let fixedBills = [];

function drawFixedBills(bills, total) {
  fixedBills = bills;
  const count = bills.length;
  byId("fixed-summary").textContent = count === 0
    ? "No fixed bills yet. Tick “Repeats every month” when you add rent, phone or Wi-Fi."
    : count + (count === 1 ? " bill" : " bills") + " · " + formatOut(total) + " a month";

  const tags = byId("fixed-tags");
  tags.replaceChildren();
  bills.forEach((bill) => tags.append(makeElement("span", "tag", bill.note || bill.category)));
}

function openFixedBillsList() {
  showExpenseList("Fixed bills", fixedBills, "These are added to every month automatically.", true);
}

// ===== RECENT + SEE ALL =====
function drawRecent(expenses) {
  const list = byId("recent-list");
  list.replaceChildren();
  if (expenses.length === 0) {
    list.append(makeElement("li", "empty", "No spending this month yet."));
    return;
  }
  expenses.forEach((expense) => list.append(makeExpenseItem(expense)));
}

async function openAllExpenses() {
  try {
    const data = await getExpenses(shownMonth);
    showExpenseList("All expenses · " + formatMonthName(shownMonth), data.everyday, "Tap one to edit or delete it.", false);
  } catch (error) {
    showToast(error.message, true);
  }
}

// One expense row: name + category/date on the left, "−Rs 245" on the right. Tap to edit.
function makeExpenseItem(expense) {
  const li = makeElement("li");
  const button = makeElement("button", "item");
  button.type = "button";

  const left = makeElement("span");
  left.append(makeElement("span", "item-name", expense.note || expense.category));
  const when = expense.is_fixed ? "Every month" : formatShortDate(expense.date);
  left.append(makeElement("span", "item-sub", expense.category + " · " + when));

  button.append(left, makeElement("span", "item-amount money-out", formatOut(expense.amount)));
  button.addEventListener("click", () => openExpenseSheet(expense));
  li.append(button);
  return li;
}

// Fills the list pop-up (used by "See all" and "View or edit bills")
function showExpenseList(title, expenses, hint, isFixedList) {
  byId("list-title").textContent = title;
  byId("list-hint").textContent = hint;
  byId("list-add-btn").hidden = !isFixedList;
  const list = byId("list-items");
  list.replaceChildren();
  if (expenses.length === 0) {
    list.append(makeElement("li", "empty", "Nothing here yet."));
  }
  expenses.forEach((expense) => list.append(makeExpenseItem(expense)));
  openSheet("sheet-list");
}

// ===== ADD / EDIT EXPENSE POP-UP =====
function buildCategoryGrid() {
  const grid = byId("category-grid");
  grid.replaceChildren();
  categoryList.forEach((row) => {
    const button = makeElement("button", "choice", row.category);
    button.type = "button";
    button.dataset.category = row.category;
    button.addEventListener("click", () => pickCategory(row.category, true));
    grid.append(button);
  });
}

// Picking a category also pre-picks Need/Want from it (the user can still change it after)
function pickCategory(category, setKindToo) {
  chosenCategory = category;
  document.querySelectorAll("#category-grid .choice").forEach((button) => {
    const isChosen = button.dataset.category === category;
    button.classList.toggle("active", isChosen);
    button.setAttribute("aria-pressed", isChosen);
  });
  if (setKindToo) {
    const row = categoryList.find((r) => r.category === category);
    pickKind(row ? row.default_kind : "need");
  }
}

function pickKind(kind) {
  chosenKind = kind;
  document.querySelectorAll("[data-kind]").forEach((button) => {
    const isChosen = button.dataset.kind === kind;
    button.classList.toggle("active", isChosen);
    button.setAttribute("aria-pressed", isChosen);
  });
}

// expense = null → empty "Add expense" form. Otherwise the form is filled in for editing.
// startFixed = true → "Repeats every month" is ticked (used by "+ Add fixed bill").
function openExpenseSheet(expense, startFixed) {
  buildCategoryGrid();
  editingExpenseId = expense ? expense.id : null;
  byId("expense-title").textContent = expense ? "Edit expense" : "Add expense";
  byId("expense-delete").hidden = !expense;
  byId("expense-error").textContent = "";

  byId("expense-amount").value = expense ? expense.amount : "";
  byId("expense-note").value = expense ? expense.note : "";
  byId("expense-date").value = expense ? expense.date : getTodayText();
  byId("expense-fixed").checked = expense ? Boolean(expense.is_fixed) : Boolean(startFixed);

  chosenCategory = null;
  chosenKind = null;
  document.querySelectorAll("#category-grid .choice, [data-kind]").forEach((b) => b.classList.remove("active"));
  if (expense) {
    pickCategory(expense.category, false);
    pickKind(expense.kind);
  }

  openSheet("sheet-expense");
  if (!expense) byId("expense-amount").focus();
}

function readExpenseForm() {
  return {
    amount: Number(byId("expense-amount").value),
    category: chosenCategory,
    kind: chosenKind,
    note: byId("expense-note").value.trim(),
    date: byId("expense-date").value || null,
    is_fixed: byId("expense-fixed").checked,
    source: "typed",
  };
}

// Quick checks so the user gets an answer straight away (the backend checks again)
function findExpenseProblem(expense) {
  if (!(expense.amount > 0)) return "Please enter an amount above 0.";
  if (!expense.category) return "Please pick a category.";
  return "";
}

async function saveExpenseForm(event) {
  event.preventDefault();
  const expense = readExpenseForm();
  const problem = findExpenseProblem(expense);
  if (problem) {
    showFormError("expense-error", problem);
    return;
  }

  const saveButton = byId("expense-save");
  saveButton.disabled = true;
  try {
    if (editingExpenseId === null) {
      await addExpense(expense);
      showToast("Expense saved");
    } else {
      await editExpense(editingExpenseId, expense);
      showToast("Expense updated");
    }
    closeSheet("sheet-expense");
    closeSheet("sheet-list");
    await loadMoneyTab();
  } catch (error) {
    showFormError("expense-error", error.message);
  } finally {
    saveButton.disabled = false;
  }
}

async function deleteShownExpense() {
  const message = byId("expense-fixed").checked
    ? "Delete this fixed bill? It will be removed from every month, including past months."
    : "Delete this expense?";
  if (!confirm(message)) return;
  try {
    await deleteExpense(editingExpenseId);
    showToast("Expense deleted");
    closeSheet("sheet-expense");
    closeSheet("sheet-list");
    await loadMoneyTab();
  } catch (error) {
    showFormError("expense-error", error.message);
  }
}

// ===== MONEY IN: REGULAR + ONE-OFF INCOME =====
const FREQUENCY_NAMES = { monthly: "Monthly", weekly: "Weekly", "one-off": "One-off" };

function drawIncomeLists(regular, oneOff) {
  fillIncomeList("regular-list", regular, "No regular income yet. Add your salary, allowance or side hustle.");
  fillIncomeList("one-off-list", oneOff, "Gifts, freelance jobs or prizes you got this month go here.");
}

function fillIncomeList(listId, incomes, emptyText) {
  const list = byId(listId);
  list.replaceChildren();
  if (incomes.length === 0) {
    list.append(makeElement("li", "empty", emptyText));
    return;
  }
  incomes.forEach((income) => list.append(makeIncomeItem(income)));
}

// One income row: name (+ "Auto" tag if it repeats), type and how often, "+Rs 15,000" on the right
function makeIncomeItem(income) {
  const li = makeElement("li");
  const button = makeElement("button", "item");
  button.type = "button";

  const left = makeElement("span");
  const name = makeElement("span", "item-name", income.name);
  let sub = income.type + " · ";
  if (income.frequency === "one-off") {
    sub += formatShortDate(income.date);
  } else {
    name.append(makeElement("span", "auto-tag", "Auto"));
    sub += FREQUENCY_NAMES[income.frequency];
    if (income.frequency === "weekly") sub += " · ≈ " + formatMoney(Math.round(income.per_month)) + " a month";
  }
  left.append(name, makeElement("span", "item-sub", sub));

  button.append(left, makeElement("span", "item-amount money-in", formatIn(income.amount)));
  button.addEventListener("click", () => openIncomeSheet(income));
  li.append(button);
  return li;
}

// ===== ADD / EDIT INCOME POP-UP =====
function buildIncomeTypeGrid() {
  const grid = byId("income-type-grid");
  grid.replaceChildren();
  incomeTypes.forEach((type) => {
    const button = makeElement("button", "choice", type);
    button.type = "button";
    button.dataset.incomeType = type;
    button.addEventListener("click", () => pickIncomeType(type));
    grid.append(button);
  });
}

function pickIncomeType(type) {
  chosenIncomeType = type;
  document.querySelectorAll("[data-income-type]").forEach((button) => {
    const isChosen = button.dataset.incomeType === type;
    button.classList.toggle("active", isChosen);
    button.setAttribute("aria-pressed", isChosen);
  });
}

// The date means "starts on" for repeating income and "date received" for a one-off
function pickFrequency(frequency) {
  chosenFrequency = frequency;
  document.querySelectorAll("[data-frequency]").forEach((button) => {
    const isChosen = button.dataset.frequency === frequency;
    button.classList.toggle("active", isChosen);
    button.setAttribute("aria-pressed", isChosen);
  });
  byId("income-date-label").textContent = frequency === "one-off" ? "Date received" : "Starts on";
}

// income = null → empty form. startFrequency → which "How often?" button is picked at the start.
function openIncomeSheet(income, startFrequency) {
  buildIncomeTypeGrid();
  editingIncomeId = income ? income.id : null;
  byId("income-title").textContent = income ? "Edit income" : "Add income";
  byId("income-delete").hidden = !income;
  byId("income-error").textContent = "";

  byId("income-name").value = income ? income.name : "";
  byId("income-amount").value = income ? income.amount : "";
  byId("income-date").value = income ? income.date : getTodayText();

  chosenIncomeType = null;
  if (income) pickIncomeType(income.type);
  pickFrequency(income ? income.frequency : startFrequency || "monthly");

  openSheet("sheet-income");
  if (!income) byId("income-name").focus();
}

function readIncomeForm() {
  return {
    name: byId("income-name").value.trim(),
    type: chosenIncomeType,
    amount: Number(byId("income-amount").value),
    frequency: chosenFrequency,
    date: byId("income-date").value,
  };
}

// Quick checks so the user gets an answer straight away (the backend checks again)
function findIncomeProblem(income) {
  if (!income.name) return "Please give the income a name.";
  if (!income.type) return "Please pick a type.";
  if (!(income.amount > 0)) return "Please enter an amount above 0.";
  if (!income.date) return "Please pick a date.";
  return "";
}

async function saveIncomeForm(event) {
  event.preventDefault();
  const income = readIncomeForm();
  const problem = findIncomeProblem(income);
  if (problem) {
    showFormError("income-error", problem);
    return;
  }

  const saveButton = byId("income-save");
  saveButton.disabled = true;
  try {
    if (editingIncomeId === null) {
      await addIncome(income);
      showToast("Income saved");
    } else {
      await editIncome(editingIncomeId, income);
      showToast("Income updated");
    }
    closeSheet("sheet-income");
    await loadMoneyTab();
  } catch (error) {
    showFormError("income-error", error.message);
  } finally {
    saveButton.disabled = false;
  }
}

async function deleteShownIncome() {
  const message = chosenFrequency === "one-off"
    ? "Delete this income?"
    : "Delete this regular income? It will be removed from every month, including past months.";
  if (!confirm(message)) return;
  try {
    await deleteIncome(editingIncomeId);
    showToast("Income deleted");
    closeSheet("sheet-income");
    await loadMoneyTab();
  } catch (error) {
    showFormError("income-error", error.message);
  }
}

// ===== SET BUDGET POP-UP =====
function openBudgetSheet(category, currentLimit) {
  budgetCategory = category;
  byId("budget-title").textContent = "Budget: " + category;
  byId("budget-amount").value = currentLimit === null ? "" : currentLimit;
  byId("budget-remove").hidden = currentLimit === null;
  byId("budget-error").textContent = "";
  openSheet("sheet-budget");
  byId("budget-amount").focus();
}

async function saveBudgetForm(event) {
  event.preventDefault();
  const limit = Number(byId("budget-amount").value);
  if (!(limit > 0)) {
    showFormError("budget-error", "Please enter an amount above 0.");
    return;
  }
  await sendBudget(limit, "Budget saved");
}

async function removeBudget() {
  await sendBudget(null, "Budget removed");
}

async function sendBudget(limit, doneMessage) {
  try {
    await setBudget(budgetCategory, limit);
    showToast(doneMessage);
    closeSheet("sheet-budget");
    await loadMoneyTab();
  } catch (error) {
    showFormError("budget-error", error.message);
  }
}

// ===== MONEY IN / MONEY OUT SWITCH =====
function showMoneyView(view) {
  const isOut = view === "out";
  byId("view-out").hidden = !isOut;
  byId("view-in").hidden = isOut;
  byId("switch-out").classList.toggle("active", isOut);
  byId("switch-in").classList.toggle("active", !isOut);
  byId("switch-out").setAttribute("aria-selected", isOut);
  byId("switch-in").setAttribute("aria-selected", !isOut);
}

// ===== START (called by app.js once you're logged in) =====
function startMoneyTab() {
  byId("month-prev").addEventListener("click", () => changeMonth(-1));
  byId("month-next").addEventListener("click", () => changeMonth(1));
  byId("switch-out").addEventListener("click", () => showMoneyView("out"));
  byId("switch-in").addEventListener("click", () => showMoneyView("in"));

  byId("add-expense-btn").addEventListener("click", () => openExpenseSheet(null));
  byId("mic-btn").addEventListener("click", () => openExpenseSheet(null)); // voice is added in step 6
  byId("fixed-open").addEventListener("click", openFixedBillsList);
  byId("see-all-btn").addEventListener("click", openAllExpenses);
  byId("list-add-btn").addEventListener("click", () => openExpenseSheet(null, true));

  document.querySelectorAll("[data-kind]").forEach((button) => {
    button.addEventListener("click", () => pickKind(button.dataset.kind));
  });
  byId("expense-form").addEventListener("submit", saveExpenseForm);
  byId("expense-delete").addEventListener("click", deleteShownExpense);
  byId("budget-form").addEventListener("submit", saveBudgetForm);
  byId("budget-remove").addEventListener("click", removeBudget);

  byId("add-income-btn").addEventListener("click", () => openIncomeSheet(null, "monthly"));
  byId("add-one-off-btn").addEventListener("click", () => openIncomeSheet(null, "one-off"));
  document.querySelectorAll("[data-frequency]").forEach((button) => {
    button.addEventListener("click", () => pickFrequency(button.dataset.frequency));
  });
  byId("income-form").addEventListener("submit", saveIncomeForm);
  byId("income-delete").addEventListener("click", deleteShownIncome);

  loadMoneyTab();
}
