// api.js — every call to our backend (/api/...) lives here, in one place.
// Each function returns the JSON the backend sends back, or throws an Error with a friendly, translated message.

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
    throw new Error(t("error.OFFLINE"));
  }

  if (res.status === 401) {
    window.location.href = "login.html"; // session ended: log in again
    throw new Error(t("error.NOT_LOGGED_IN"));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(readErrorMessage(data));
  }
  return data;
}

// The backend sends {detail, code, params} (see backend/errors.py). We show the translated code
// ("error.<CODE>" in lang/*.json) and fall back to the backend's English message if the code is unknown.
function readErrorMessage(data) {
  if (data.code && I18n.hasKey("error." + data.code)) return t("error." + data.code, formatErrorParams(data.params));
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    return data.detail[0].msg.replace("Value error, ", "");
  }
  return t("error.GENERIC");
}

// Money values inside error texts are shown as "Rs 1,234"
function formatErrorParams(params) {
  const result = Object.assign({}, params);
  if (typeof result.saved === "number") result.saved = formatMoney(result.saved);
  if (typeof result.over === "number") result.over = formatMoney(result.over); // game: over income
  return result;
}

// ===== LOGIN =====
function getMe() { return callApi("GET", "/api/auth/me"); }
function logOut() { return callApi("POST", "/api/auth/logout"); }
function saveMyLanguage(language) { return callApi("PUT", "/api/auth/language", { language: language }); } // en / fr / mfe

// ===== MONEY TAB =====
function getSummary(month) { return callApi("GET", "/api/summary?month=" + month); }

// category is optional: only that category's expenses
function getExpenses(month, category) {
  const filter = category ? "&category=" + encodeURIComponent(category) : "";
  return callApi("GET", "/api/expenses?month=" + month + filter);
}
function addExpense(expense) { return callApi("POST", "/api/expenses", expense); }
function editExpense(id, expense) { return callApi("PUT", "/api/expenses/" + id, expense); }
function deleteExpense(id) { return callApi("DELETE", "/api/expenses/" + id); }

function getQuickAdd() { return callApi("GET", "/api/expenses/quick"); }
function addQuickExpense(chip) {
  return callApi("POST", "/api/expenses/quick", { note: chip.note, amount: chip.amount });
}

function getBudgets(month) { return callApi("GET", "/api/budgets?month=" + month); }
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
// Inflation estimate (Statistics Mauritius CPI): one saved goal, or a live preview for the goal form
function getGoalInflation(id) { return callApi("GET", "/api/goals/" + id + "/inflation-projection"); }
// Live preview for the goal form: { target, current, deadline, category }
function getInflationPreview(query) { return callApi("GET", "/api/inflation/projection?" + new URLSearchParams(query)); }

// ===== LOANS TAB =====
// details = { monthly_income, monthly_expenses, existing_debt_payment, interest_rate, years, missed_payment }
function predictLoan(details) { return callApi("POST", "/api/loans/predict", details); }
function addMoneyToGoal(id, amount) { return callApi("POST", "/api/goals/" + id + "/add-money", { amount: amount }); }

// ===== ARCADE: BUDGET CHALLENGE (scores and XP are worked out on the server) =====
function getGameLevels() { return callApi("GET", "/api/game/levels"); }
function startGameAttempt(level, eventsOn) {
  return callApi("POST", "/api/game/attempts", { level: level, events_on: eventsOn });
}
// isFinal false = first try (the server then reveals the surprise event), true = final submit (score + XP)
function submitGameAttempt(attemptId, allocation, isFinal) {
  return callApi("POST", "/api/game/attempts/" + attemptId + "/submit", { allocation: allocation, final: isFinal });
}
function getGameAttempts() { return callApi("GET", "/api/game/attempts"); }
