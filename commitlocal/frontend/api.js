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
  if (typeof result.short === "number") result.short = formatMoney(result.short); // game: event shortfall
  if (typeof result.available === "number") result.available = formatMoney(result.available); // savings: take out
  if (typeof result.left === "number") result.left = formatMoney(result.left); // savings: what a goal still needs
  return result;
}

// ===== LOGIN =====
function getMe() { return callApi("GET", "/api/auth/me"); }
function logOut() { return callApi("POST", "/api/auth/logout"); }
function saveMyLanguage(language) { return callApi("PUT", "/api/auth/language", { language: language }); } // en / fr / mfe

// ===== PROFILE TAB (always the logged-in user's own account; the password hash is never sent) =====
function getProfile() { return callApi("GET", "/api/profile"); }
function saveProfileUsername(username) { return callApi("PUT", "/api/profile/username", { username: username }); }
// needs the current password
function saveProfileEmail(email, currentPassword) {
  return callApi("PUT", "/api/profile/email", { email: email, current_password: currentPassword });
}
function saveProfileOccupation(occupation) { return callApi("PUT", "/api/profile/occupation", { occupation: occupation }); }
function changeMyPassword(current, newPassword, confirm) {
  return callApi("PUT", "/api/profile/password",
    { current_password: current, new_password: newPassword, confirm_password: confirm });
}

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

// Guessed category for a note ("KFC 350") — own history first, then keywords. Nothing is saved.
function suggestCategory(text) { return callApi("GET", "/api/expenses/suggest-category?text=" + encodeURIComponent(text)); }
// 📷 Scan bill: image = a data URL; the answer only fills in the form (nothing is saved)
function scanBill(image) { return callApi("POST", "/api/expenses/scan-bill", { image: image }); }
function getCategoryKeywords() { return callApi("GET", "/api/expenses/category-keywords"); } // kept on the phone for offline
// Spending forecast + goal ready-by months (plain maths). today = the phone's local date.
function getForecast(today, month) { return callApi("GET", "/api/forecast?today=" + today + "&month=" + month); }

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

// ===== OPTIONAL INFORMATION ("I have none") + SAVED LOANS =====
// Each topic is provided / none / missing. Missing is never shown as Rs 0.
function getInfoStatus(month) { return callApi("GET", "/api/info-status?month=" + month); }
// topic: income / expenses (per month) or loans / savings; none: true = "I have none", false = undo
function setInfoChoice(topic, month, none) {
  return callApi("PUT", "/api/info-choices", { topic: topic, month: month || null, none: none });
}
function getMyLoans() { return callApi("GET", "/api/my-loans"); }
// loan = { name, balance, annual_rate, monthly_payment, start_date }
function addMyLoan(loan) { return callApi("POST", "/api/my-loans", loan); }
function editMyLoan(id, loan) { return callApi("PUT", "/api/my-loans/" + id, loan); }
function deleteMyLoan(id) { return callApi("DELETE", "/api/my-loans/" + id); }

// ===== DASHBOARD (plain maths on the server, never the AI) =====
// today = the phone's local date "YYYY-MM-DD" (weeks and months follow the user's own day)
function getDashboard(today) { return callApi("GET", "/api/dashboard?today=" + today); }
function setWeeklyBudget(amount, today) { return callApi("PUT", "/api/dashboard/weekly-budget", { amount: amount, today: today }); }

// ===== FINANCIAL INSIGHTS =====
// getInsights only reads (never calls the AI). generateInsights is used ONLY by the button.
function getInsights(month) { return callApi("GET", "/api/insights?month=" + month); }
function generateInsights(month) { return callApi("POST", "/api/insights/generate", { month: month }); }
function getQuickInsights(month) { return callApi("POST", "/api/insights/quick", { month: month }); } // never calls the AI

// ===== MONEY → SAVINGS (was the Targets tab) =====
function getSavings() { return callApi("GET", "/api/savings"); }
function updateSavings(bankBalance, monthlyTarget) {
  return callApi("PUT", "/api/savings", { bank_balance: bankBalance, monthly_target: monthlyTarget });
}
// Real savings: "Add to savings" / "Take out" entries (they move total savings and the safety net / goal picked)
function getSavingsEntries(month) { return callApi("GET", "/api/savings/entries?month=" + month); }
function addSavingsEntry(entry) { return callApi("POST", "/api/savings/entries", entry); }
function editSavingsEntry(id, entry) { return callApi("PUT", "/api/savings/entries/" + id, entry); }
function deleteSavingsEntry(id) { return callApi("DELETE", "/api/savings/entries/" + id); }

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

// ===== MY BUDGET PLAN (rules are checked by the backend; today = the phone's local date) =====
function getPlan(today) { return callApi("GET", "/api/plan?today=" + encodeURIComponent(today)); }
function previewStartPlan(answers) { return callApi("POST", "/api/plan/start/preview", answers); }
function startPlan(answers) { return callApi("POST", "/api/plan/start", answers); }
function previewPlanChange(planId, today) {
  return callApi("GET", "/api/plan/preview?plan_id=" + encodeURIComponent(planId) + "&today=" + encodeURIComponent(today));
}
function changePlan(change) { return callApi("POST", "/api/plan/change", change); }
function cancelPlanChange(today) { return callApi("DELETE", "/api/plan/pending?today=" + encodeURIComponent(today)); }
