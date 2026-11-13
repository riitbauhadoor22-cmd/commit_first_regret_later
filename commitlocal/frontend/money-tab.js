// money-tab.js — draws the Money tab (budget bar, expense list) and runs the Expenses pop-up (Add expense / Set budget).

// ===== STATE =====
const CATEGORIES = ["Food & drinks", "Groceries", "Transport", "Shopping", "Bills", "Utilities",
  "Subscriptions", "Fun & outings", "Other"]; // same list as backend/categories.py
const MAX_AMOUNT = 10000000;

// ===== API CALLS =====
async function loadMoneyTab() {
  const [expenses, budget] = await Promise.all([
    callApi("GET", "/api/expenses"),
    callApi("GET", "/api/budget"),
  ]);
  if (expenses.ok) drawExpenses(expenses.data);
  if (budget.ok) drawBudget(budget.data);
}

async function saveExpense(event) {
  event.preventDefault(); // stay on the page (no form reload)
  const amount = readAmount("exp-amount", "expense-msg");
  if (amount === null) return;
  const button = event.submitter;
  button.disabled = true;
  const result = await callApi("POST", "/api/expenses", {
    amount: amount,
    category: byId("exp-category").value,
    note: byId("exp-note").value.trim(),
    date: byId("exp-date").value || null, // empty → backend uses today
  });
  button.disabled = false;
  if (!result.ok) return (byId("expense-msg").textContent = result.message);
  closeModal("expense-modal");
  loadMoneyTab(); // refresh list and totals straight away
}

async function saveBudget(event) {
  event.preventDefault();
  const amount = readAmount("budget-amount", "budget-msg");
  if (amount === null) return;
  const button = event.submitter;
  button.disabled = true;
  const result = await callApi("PUT", "/api/budget", { monthly_limit: amount });
  button.disabled = false;
  if (!result.ok) return (byId("budget-msg").textContent = result.message);
  closeModal("expense-modal");
  loadMoneyTab();
}

// ===== VALIDATION =====
// The amount as a number, or null (and an error message) if it's empty, zero, negative or huge
function readAmount(inputId, messageId) {
  const text = byId(inputId).value.trim();
  const amount = Number(text);
  let problem = "";
  if (text === "" || isNaN(amount)) problem = "Please enter an amount.";
  else if (amount <= 0) problem = "The amount must be more than Rs 0.";
  else if (amount > MAX_AMOUNT) problem = "That amount is too big.";
  byId(messageId).textContent = problem;
  return problem ? null : Math.round(amount * 100) / 100;
}

// ===== UI =====
function drawBudget(data) {
  const bar = byId("budget-bar");
  const warning = byId("budget-warning");
  if (!data.monthly_limit) {
    byId("budget-text").textContent = "Spent " + formatRs(data.spent) + " · no budget set yet";
    bar.style.width = "0";
    warning.hidden = true;
    return;
  }
  const percent = (data.spent / data.monthly_limit) * 100;
  byId("budget-text").textContent = "Spent " + formatRs(data.spent) + " of " + formatRs(data.monthly_limit);
  bar.style.width = Math.min(percent, 100) + "%";
  // green under 75%, orange 75–100%, red when over budget
  bar.className = "progress-bar " + (percent > 100 ? "bar-red" : percent >= 75 ? "bar-orange" : "bar-green");
  warning.hidden = data.over_by <= 0;
  warning.textContent = "⚠ Over budget by " + formatRs(data.over_by);
}

function drawExpenses(data) {
  byId("expenses-total").textContent = formatRs(data.total);
  byId("expense-empty").hidden = data.expenses.length > 0;
  const list = byId("expense-list");
  list.innerHTML = "";
  data.expenses.forEach((e) => {
    const li = document.createElement("li");
    const left = document.createElement("span");
    left.textContent = (e.note || e.category) + " · " + e.date.slice(8) + "/" + e.date.slice(5, 7); // textContent = safe from HTML in notes
    const right = document.createElement("span");
    right.className = "amount-out";
    right.textContent = "−" + formatRs(e.amount);
    li.append(left, right);
    list.append(li);
  });
}

// Show one view inside the pop-up: "choice", "expense" or "budget"
function showModalView(view) {
  byId("modal-choice").hidden = view !== "choice";
  byId("expense-form").hidden = view !== "expense";
  byId("budget-form").hidden = view !== "budget";
  byId("modal-title").textContent = { choice: "Expenses", expense: "Add expense", budget: "Set budget" }[view];
}

function openExpensesPopup() {
  byId("expense-form").reset();
  byId("budget-form").reset();
  byId("exp-date").value = todayString();
  byId("expense-msg").textContent = "";
  byId("budget-msg").textContent = "";
  showModalView("choice");
  openModal("expense-modal");
}

// ===== START =====
byId("exp-category").innerHTML = CATEGORIES.map((c) => "<option>" + c + "</option>").join("");
setUpModal("expense-modal");
byId("expenses-card").addEventListener("click", openExpensesPopup);
byId("choose-expense").addEventListener("click", () => {
  showModalView("expense");
  byId("exp-amount").focus();
});
byId("choose-budget").addEventListener("click", () => {
  showModalView("budget");
  byId("budget-amount").focus();
});
byId("expense-form").addEventListener("submit", saveExpense);
byId("budget-form").addEventListener("submit", saveBudget);
loadMoneyTab();
