// money-tab.js — the Money tab: month picker, dark summary card, Money in / Money out switch,
// Money out (quick-add chips, category budgets, fixed bills, recent expenses), Money in (regular and
// one-off income), and the Add expense, Add income and Set budget pop-ups. All the maths comes from the backend (/api/summary).
// Tapping a category row opens its own pop-up: spent vs budget, set the budget, add / edit / delete its expenses.
// The spent-vs-budget numbers and colours come from budget-calc.js (BudgetCalc.budgetProgress).
// Texts come from i18n.js: t("key"). Category / income type VALUES stay English (the API needs them); only the display is translated.

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
let detailCategory = null;    // which category the category pop-up shows
let detailEditingId = null;   // expense being edited in the category pop-up (null = adding)
let detailEditingKind = null; // keep its Need/Want when editing

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
    makeLegendItem("split-needs", t("money.needsPercent", { n: Math.round(needs) })),
    makeLegendItem("split-wants", t("money.wantsPercent", { n: Math.round(wants) })),
    makeLegendItem("split-savings", t("money.savingsPercent", { n: Math.round(savings) })),
    makeElement("span", "aim", t("money.aim"))
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
    button.setAttribute("aria-label", t("money.quickAddAria", { name: chip.label }));
    button.addEventListener("click", () => saveQuickExpense(chip, button));
    box.append(button);
  });
}

async function saveQuickExpense(chip, button) {
  button.disabled = true; // stops a double tap saving it twice
  try {
    await addQuickExpense(chip);
    showToast(t("toast.added", { name: chip.label }));
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
  const item = makeElement("div", "cat-row tappable");
  // The whole row opens the category pop-up (role=button so screen readers and keyboards can use it)
  item.setAttribute("role", "button");
  item.tabIndex = 0;
  item.setAttribute("aria-label", t("money.openCategory", { name: tCategory(row.category) }));
  item.addEventListener("click", () => openCategorySheet(row.category));
  item.addEventListener("keydown", (event) => {
    if (event.target === item && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openCategorySheet(row.category);
    }
  });
  const progress = BudgetCalc.budgetProgress(row.spent, row.budget);
  const top = makeElement("div", "cat-top");
  top.append(makeElement("span", "cat-name", tCategory(row.category)));

  // Right side: "Rs 2,300 / Rs 4,000"  or  "Rs 190  Set budget"
  const right = makeElement("span", "cat-right");
  const amount = makeElement("span", "cat-amount");
  amount.append(makeElement("strong", "", formatMoney(progress.spent)));
  right.append(amount);
  top.append(right);
  item.append(top);

  if (!progress.hasBudget) {
    right.append(makeBudgetLink("budget.set", row.category, null)); // no budget: no bar
    return item;
  }
  amount.append(" / " + formatMoney(progress.budget));

  // Bar colour: blue under 80%, amber 80-100%, red over budget
  const bar = makeElement("div", "bar " + progress.level);
  const fill = makeElement("span");
  fill.style.width = progress.barPercent + "%";
  bar.append(fill);
  item.append(bar);

  // Under the bar: the warning (if over budget) on the left, "Edit" on the right
  const bottom = makeElement("div", "cat-bottom");
  const warning = progress.over > 0 ? "⚠ " + t("budget.overBy", { amount: formatMoney(progress.over) }) : "";
  bottom.append(makeElement("p", "warn", warning), makeBudgetLink("common.edit", row.category, progress.budget));
  item.append(bottom);
  return item;
}

// key = "budget.set" or "common.edit"
function makeBudgetLink(key, category, currentLimit) {
  const link = makeElement("button", "link-btn", t(key));
  link.type = "button";
  const ariaKey = key === "common.edit" ? "budget.editFor" : "budget.setFor";
  link.setAttribute("aria-label", t(ariaKey, { name: tCategory(category) }));
  link.addEventListener("click", (event) => {
    event.stopPropagation(); // the row behind would open the same pop-up a second time
    openCategorySheet(category, true);
  });
  return link;
}

// ===== FIXED MONTHLY BILLS =====
let fixedBills = [];

function drawFixedBills(bills, total) {
  fixedBills = bills;
  const count = bills.length;
  byId("fixed-summary").textContent = count === 0
    ? t("money.fixedEmpty")
    : t(count === 1 ? "money.billOne" : "money.billMany", { count: count, amount: formatOut(total) });

  const tags = byId("fixed-tags");
  tags.replaceChildren();
  bills.forEach((bill) => tags.append(makeElement("span", "tag", bill.note || tCategory(bill.category))));
}

function openFixedBillsList() {
  showExpenseList(t("money.fixedBills"), fixedBills, t("money.fixedHint"), true);
}

// ===== RECENT + SEE ALL =====
function drawRecent(expenses) {
  const list = byId("recent-list");
  list.replaceChildren();
  if (expenses.length === 0) {
    list.append(makeElement("li", "empty", t("money.noSpending")));
    return;
  }
  expenses.forEach((expense) => list.append(makeExpenseItem(expense)));
}

async function openAllExpenses() {
  try {
    const data = await getExpenses(shownMonth);
    showExpenseList(t("money.allExpenses") + " · " + formatMonthName(shownMonth), data.everyday, t("common.tapToEdit"), false);
  } catch (error) {
    showToast(error.message, true);
  }
}

// One expense row: name + category/date on the left, "−Rs 245" on the right. Tap to edit.
// onTap (optional) replaces the normal "open the Edit expense pop-up".
function makeExpenseItem(expense, onTap) {
  const li = makeElement("li");
  const button = makeElement("button", "item");
  button.type = "button";

  const left = makeElement("span");
  left.append(makeElement("span", "item-name", expense.note || tCategory(expense.category)));
  const when = expense.is_fixed ? t("money.everyMonth") : formatShortDate(expense.date);
  left.append(makeElement("span", "item-sub", tCategory(expense.category) + " · " + when));

  button.append(left, makeElement("span", "item-amount money-out", formatOut(expense.amount)));
  button.addEventListener("click", () => (onTap || openExpenseSheet)(expense));
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
    list.append(makeElement("li", "empty", t("common.nothingYet")));
  }
  expenses.forEach((expense) => list.append(makeExpenseItem(expense)));
  openSheet("sheet-list");
}

// ===== ADD / EDIT EXPENSE POP-UP =====
function buildCategoryGrid() {
  const grid = byId("category-grid");
  grid.replaceChildren();
  categoryList.forEach((row) => {
    const button = makeElement("button", "choice");
    setValueText(button, I18n.CATEGORY_KEYS, row.category);
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
  setText(byId("expense-title"), expense ? "expense.edit" : "expense.add");
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
  if (!(expense.amount > 0)) return t("form.amountAbove0");
  if (!expense.category) return t("form.pickCategory");
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
      showToast(t("toast.expenseSaved"));
    } else {
      await editExpense(editingExpenseId, expense);
      showToast(t("toast.expenseUpdated"));
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
  const message = byId("expense-fixed").checked ? t("confirm.deleteFixedBill") : t("confirm.deleteExpense");
  if (!confirm(message)) return;
  try {
    await deleteExpense(editingExpenseId);
    showToast(t("toast.expenseDeleted"));
    closeSheet("sheet-expense");
    closeSheet("sheet-list");
    await loadMoneyTab();
  } catch (error) {
    showFormError("expense-error", error.message);
  }
}

// ===== MONEY IN: REGULAR + ONE-OFF INCOME =====
const FREQUENCY_KEYS = { monthly: "freq.monthly", weekly: "freq.weekly", "one-off": "freq.oneOff" };

function drawIncomeLists(regular, oneOff) {
  fillIncomeList("regular-list", regular, t("income.regularEmpty"));
  fillIncomeList("one-off-list", oneOff, t("income.oneOffEmpty"));
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
  let sub = tIncomeType(income.type) + " · ";
  if (income.frequency === "one-off") {
    sub += formatShortDate(income.date);
  } else {
    name.append(makeElement("span", "auto-tag", t("income.auto")));
    sub += t(FREQUENCY_KEYS[income.frequency]);
    if (income.frequency === "weekly") sub += " · ≈ " + t("common.perMonth", { amount: formatMoney(Math.round(income.per_month)) });
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
    const button = makeElement("button", "choice");
    setValueText(button, I18n.INCOME_TYPE_KEYS, type);
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
  setText(byId("income-date-label"), frequency === "one-off" ? "income.dateReceived" : "income.startsOn");
}

// income = null → empty form. startFrequency → which "How often?" button is picked at the start.
function openIncomeSheet(income, startFrequency) {
  buildIncomeTypeGrid();
  editingIncomeId = income ? income.id : null;
  setText(byId("income-title"), income ? "income.edit" : "income.add");
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
  if (!income.name) return t("form.incomeName");
  if (!income.type) return t("form.pickType");
  if (!(income.amount > 0)) return t("form.amountAbove0");
  if (!income.date) return t("form.pickDate");
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
      showToast(t("toast.incomeSaved"));
    } else {
      await editIncome(editingIncomeId, income);
      showToast(t("toast.incomeUpdated"));
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
  const message = chosenFrequency === "one-off" ? t("confirm.deleteIncome") : t("confirm.deleteRegularIncome");
  if (!confirm(message)) return;
  try {
    await deleteIncome(editingIncomeId);
    showToast(t("toast.incomeDeleted"));
    closeSheet("sheet-income");
    await loadMoneyTab();
  } catch (error) {
    showFormError("income-error", error.message);
  }
}

// ===== SET BUDGET POP-UP =====
function openBudgetSheet(category, currentLimit) {
  budgetCategory = category;
  setText(byId("budget-title"), "budget.titleFor", { name: tCategory(category) });
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
    showFormError("budget-error", t("form.amountAbove0"));
    return;
  }
  await sendBudget(limit, t("toast.budgetSaved"));
}

async function removeBudget() {
  await sendBudget(null, t("toast.budgetRemoved"));
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

// ===== CATEGORY POP-UP (spent vs budget, budget, add / edit / delete expenses) =====
// focusBudget = true → opened from "Set budget" / "Edit": the cursor goes to the budget box
async function openCategorySheet(category, focusBudget) {
  detailCategory = category;
  setValueText(byId("cat-sheet-title"), I18n.CATEGORY_KEYS, category);
  byId("cat-sheet-month").textContent = formatMonthName(shownMonth);
  fillCategoryBudgetBox();
  byId("cat-budget-error").textContent = "";
  resetCategoryExpenseForm();
  drawCategoryProgress();
  byId("cat-sheet-list").replaceChildren(makeElement("li", "empty", t("common.loading")));
  openSheet("sheet-category");
  if (focusBudget) byId("cat-budget-amount").focus();
  await loadCategoryExpenses();
}

// The last summary row of the shown category ({} if not found, so nothing is undefined)
function getDetailRow() {
  return categoryList.find((r) => r.category === detailCategory) || {};
}

// Budget box = current monthly budget, or empty when there is none
function fillCategoryBudgetBox() {
  const budget = BudgetCalc.toAmount(getDetailRow().budget);
  byId("cat-budget-amount").value = budget > 0 ? budget : "";
}

// "Rs 3,200 of Rs 5,000" + bar + "Rs 1,800 left" / "Rs 700 over budget"
function drawCategoryProgress() {
  const row = getDetailRow();
  const progress = BudgetCalc.budgetProgress(row.spent, row.budget);
  const bar = byId("cat-sheet-bar");
  const leftText = byId("cat-sheet-left");
  bar.hidden = !progress.hasBudget;
  leftText.classList.toggle("over", progress.over > 0);
  if (!progress.hasBudget) {
    byId("cat-sheet-amounts").textContent = t("budget.spent", { amount: formatMoney(progress.spent) });
    leftText.textContent = t("budget.noneYet");
    return;
  }
  byId("cat-sheet-amounts").textContent = t("common.amountOf", { a: formatMoney(progress.spent), b: formatMoney(progress.budget) });
  bar.className = "bar " + progress.level; // blue / amber / red
  bar.firstElementChild.style.width = progress.barPercent + "%";
  leftText.textContent = progress.over > 0
    ? t("budget.over", { amount: formatMoney(progress.over) })
    : t("budget.left", { amount: formatMoney(progress.left) });
}

// This month's expenses in the category: everyday ones (newest first), then its fixed bills
async function loadCategoryExpenses() {
  const category = detailCategory;
  const list = byId("cat-sheet-list");
  try {
    const data = await getExpenses(shownMonth, category);
    if (category !== detailCategory) return; // the user already opened another category
    list.replaceChildren();
    const all = data.everyday.concat(data.fixed);
    if (all.length === 0) list.append(makeElement("li", "empty", t("budget.noSpendingIn", { name: tCategory(category) })));
    all.forEach((expense) => list.append(makeExpenseItem(expense, startEditInCategory)));
    setText(byId("cat-sheet-hint"), data.fixed.length > 0 ? "budget.hintWithFixed" : "common.tapToEdit");
  } catch (error) {
    list.replaceChildren(makeElement("li", "empty", error.message));
  }
}

// After any change: reload the whole tab (summary card, rows, recent), then this pop-up
async function refreshAfterCategoryChange() {
  await loadMoneyTab();
  if (byId("sheet-category").hidden) return;
  drawCategoryProgress();
  await loadCategoryExpenses();
}

async function saveCategoryBudget(event) {
  event.preventDefault();
  const text = byId("cat-budget-amount").value.trim();
  const hasBudget = BudgetCalc.toAmount(getDetailRow().budget) > 0;
  const limit = text === "" ? null : Number(text); // empty box = remove the budget
  if ((limit === null && !hasBudget) || (limit !== null && !(limit > 0))) {
    showFormError("cat-budget-error", t("form.amountAbove0"));
    return;
  }
  const button = byId("cat-budget-save");
  button.disabled = true;
  try {
    await setBudget(detailCategory, limit);
    byId("cat-budget-error").textContent = "";
    showToast(limit === null ? t("toast.budgetRemoved") : t("toast.budgetSaved"));
    await refreshAfterCategoryChange();
    fillCategoryBudgetBox();
  } catch (error) {
    showFormError("cat-budget-error", error.message);
  } finally {
    button.disabled = false;
  }
}

// Back to an empty "Add expense" form (date = today, category = this one)
function resetCategoryExpenseForm() {
  detailEditingId = null;
  detailEditingKind = null;
  setText(byId("cat-expense-title"), "expense.add");
  byId("cat-expense-amount").value = "";
  byId("cat-expense-note").value = "";
  byId("cat-expense-date").value = getTodayText();
  byId("cat-expense-fixed").checked = false;
  byId("cat-expense-error").textContent = "";
  setText(byId("cat-expense-save"), "expense.saveExpense");
  byId("cat-expense-cancel").hidden = true;
  byId("cat-expense-delete").hidden = true;
}

// Tapping an expense in the list fills the form for editing
function startEditInCategory(expense) {
  detailEditingId = expense.id;
  detailEditingKind = expense.kind;
  setText(byId("cat-expense-title"), "expense.edit");
  byId("cat-expense-amount").value = expense.amount;
  byId("cat-expense-note").value = expense.note || "";
  byId("cat-expense-date").value = expense.date;
  byId("cat-expense-fixed").checked = Boolean(expense.is_fixed);
  byId("cat-expense-error").textContent = "";
  setText(byId("cat-expense-save"), "common.saveChanges");
  byId("cat-expense-cancel").hidden = false;
  byId("cat-expense-delete").hidden = false;
  byId("cat-expense-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function saveCategoryExpense(event) {
  event.preventDefault();
  const expense = {
    amount: Number(byId("cat-expense-amount").value),
    category: detailCategory,
    kind: detailEditingKind, // null when adding = the category's usual Need/Want
    note: byId("cat-expense-note").value.trim(),
    date: byId("cat-expense-date").value || null,
    is_fixed: byId("cat-expense-fixed").checked,
    source: "typed",
  };
  const problem = findExpenseProblem(expense);
  if (problem) {
    showFormError("cat-expense-error", problem);
    return;
  }
  const button = byId("cat-expense-save");
  button.disabled = true; // stops a double tap saving it twice
  try {
    if (detailEditingId === null) {
      await addExpense(expense);
      showToast(t("toast.expenseSaved"));
    } else {
      await editExpense(detailEditingId, expense);
      showToast(t("toast.expenseUpdated"));
    }
    resetCategoryExpenseForm();
    await refreshAfterCategoryChange();
  } catch (error) {
    showFormError("cat-expense-error", error.message);
  } finally {
    button.disabled = false;
  }
}

async function deleteCategoryExpense() {
  const message = byId("cat-expense-fixed").checked ? t("confirm.deleteFixedBill") : t("confirm.deleteExpense");
  if (!confirm(message)) return; // the confirm step
  try {
    await deleteExpense(detailEditingId);
    showToast(t("toast.expenseDeleted"));
    resetCategoryExpenseForm();
    await refreshAfterCategoryChange();
  } catch (error) {
    showFormError("cat-expense-error", error.message);
  }
}

// ===== LANGUAGE SWITCH =====
// Category / income type value → translated text that follows later language switches (unknown values shown as they are)
function setValueText(element, keys, value) {
  if (keys[value]) setText(element, keys[value]);
  else element.textContent = value;
}

// Called by app.js after a language switch: redraw the tab, and the category pop-up if it's open
async function redrawMoneyTab() {
  await loadMoneyTab();
  if (byId("sheet-category").hidden) return;
  byId("cat-sheet-month").textContent = formatMonthName(shownMonth);
  drawCategoryProgress();
  await loadCategoryExpenses();
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
  byId("cat-budget-form").addEventListener("submit", saveCategoryBudget);
  byId("cat-expense-form").addEventListener("submit", saveCategoryExpense);
  byId("cat-expense-cancel").addEventListener("click", resetCategoryExpenseForm);
  byId("cat-expense-delete").addEventListener("click", deleteCategoryExpense);

  byId("add-income-btn").addEventListener("click", () => openIncomeSheet(null, "monthly"));
  byId("add-one-off-btn").addEventListener("click", () => openIncomeSheet(null, "one-off"));
  document.querySelectorAll("[data-frequency]").forEach((button) => {
    button.addEventListener("click", () => pickFrequency(button.dataset.frequency));
  });
  byId("income-form").addEventListener("submit", saveIncomeForm);
  byId("income-delete").addEventListener("click", deleteShownIncome);

  loadMoneyTab();
}
