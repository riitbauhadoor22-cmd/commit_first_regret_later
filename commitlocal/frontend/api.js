// api.js — every call to our backend (/api/...) lives here, in one place.
// Each function returns the JSON the backend sends back, or throws an Error with a friendly message.

// ===== THE ONE FUNCTION THAT TALKS TO THE BACKEND =====
async function callApi(method, url, body) {
  const options = { method: method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(url, options);
  } catch (error) {
    throw new Error("No internet connection. Please try again.");
  }

  if (res.status === 401) {
    window.location.href = "login.html"; // session ended: log in again
    throw new Error("Please log in first.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(readErrorMessage(data));
  }
  return data;
}

// FastAPI sends errors as {detail: "text"} or {detail: [{msg: "text"}, ...]}
function readErrorMessage(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    return data.detail[0].msg.replace("Value error, ", "");
  }
  return "Something went wrong. Please try again.";
}

// ===== LOGIN =====
function getMe() { return callApi("GET", "/api/auth/me"); }
function logOut() { return callApi("POST", "/api/auth/logout"); }

// ===== MONEY TAB =====
function getSummary(month) { return callApi("GET", "/api/summary?month=" + month); }

function getExpenses(month) { return callApi("GET", "/api/expenses?month=" + month); }
function addExpense(expense) { return callApi("POST", "/api/expenses", expense); }
function editExpense(id, expense) { return callApi("PUT", "/api/expenses/" + id, expense); }
function deleteExpense(id) { return callApi("DELETE", "/api/expenses/" + id); }

function getQuickAdd() { return callApi("GET", "/api/expenses/quick"); }
function addQuickExpense(chip) {
  return callApi("POST", "/api/expenses/quick", { note: chip.note, amount: chip.amount });
}

function setBudget(category, monthlyLimit) {
  return callApi("PUT", "/api/budgets", { category: category, monthly_limit: monthlyLimit });
}

function getIncome(month) { return callApi("GET", "/api/income?month=" + month); }
function addIncome(income) { return callApi("POST", "/api/income", income); }
function editIncome(id, income) { return callApi("PUT", "/api/income/" + id, income); }
function deleteIncome(id) { return callApi("DELETE", "/api/income/" + id); }

// ===== TARGETS TAB =====
function getSavings() { return callApi("GET", "/api/savings"); }
function updateSavings(bankBalance, monthlyTarget) {
  return callApi("PUT", "/api/savings", { bank_balance: bankBalance, monthly_target: monthlyTarget });
}
function addToSafetyNet(amount) { return callApi("POST", "/api/savings/safety-net/add-money", { amount: amount }); }

function getGoals() { return callApi("GET", "/api/goals"); }
function addGoal(goal) { return callApi("POST", "/api/goals", goal); }
function editGoal(id, goal) { return callApi("PUT", "/api/goals/" + id, goal); }
function deleteGoal(id) { return callApi("DELETE", "/api/goals/" + id); }
function addMoneyToGoal(id, amount) { return callApi("POST", "/api/goals/" + id + "/add-money", { amount: amount }); }
