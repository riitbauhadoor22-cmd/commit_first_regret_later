// profile-tab.js — the Profile tab (it was the Arcade tab):
//   a) My account: name, username, email, phone, occupation, password (GET /api/profile + PUT /api/profile/...).
//      A value on screen only changes after the server said OK; then everything is read again from the server.
//      Also two read-only lines: is Money in / are Loans shared? (GET /api/info-status)
//   b) Weekly budget + badges (moved from the Dashboard; same GET /api/dashboard, badges are awarded there).
//      The field is pre-filled with "weekly_suggestion" (from income, bills, loans, saving or category budgets)
//      when nothing is saved; a saved value is kept and "Use suggested: Rs X" is offered instead.
//   c) Budget Challenge game (arcade-tab.js, unchanged).
//   d) Theme buttons (Blue / Dark, theme.js) — they now live in the Settings pop-up (gear, app.js), not on this page.
// The password and its hash are never sent to the browser. Texts: t("key") from i18n.js.

// ===== STATE =====
let profileData = null;     // last reply from GET /api/profile
let weeklyData = null;      // last reply from GET /api/dashboard (only weekly + badges are used here)
let profileShares = null;   // last reply from GET /api/info-status
let weekInputTyped = false; // true once the user typed in (or chose) the weekly amount: never overwrite it

const BADGE_ICONS = { FIRST_WEEK: "🥇", BUDGET_KEEPER: "🛡️", CONSISTENT_PLANNER: "📅", SAVINGS_STREAK: "🔥" };
const OCCUPATION_KEYS = ["profile.occ.student", "profile.occ.employed", "profile.occ.selfEmployed",
  "profile.occ.partTime", "profile.occ.lookingForWork", "profile.occ.other"];
const ACCOUNT_FIELDS = ["username", "email", "phone", "occupation"]; // the name field was removed: the username is shown instead
// Same rules as get_password_problems() in backend/security.py (the server checks again)
const NEW_PASSWORD_RULES = [
  { id: "pw-rule-length", test: (p) => p.length >= 8 },
  { id: "pw-rule-upper", test: (p) => /[A-Z]/.test(p) },
  { id: "pw-rule-lower", test: (p) => /[a-z]/.test(p) },
  { id: "pw-rule-number", test: (p) => /[0-9]/.test(p) },
  { id: "pw-rule-symbol", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

// ===== LOAD (called by app.js every time the tab opens) =====
async function loadProfileTab() {
  loadArcadeTab(); // arcade-tab.js: the Budget Challenge
  try {
    const [account, weekly, shares] = await Promise.all([getProfile(), getDashboard(getTodayText()),
      getInfoStatus(getThisMonthText())]);
    profileData = account;
    weeklyData = weekly;
    profileShares = shares;
    drawProfile();
    announceNewBadges(weekly.badges.new); // dashboard.js
  } catch (error) {
    showToast(error.message, true);
  }
}

function drawProfile() {
  if (profileData) drawAccount(profileData);
  if (profileShares) drawShares(profileShares);
  if (weeklyData) {
    drawWeekly(weeklyData.weekly, weeklyData.recent_weeks);
    drawBadges(weeklyData.badges);
  }
  drawThemeButtons();
}

// ===== a) MY ACCOUNT =====
function drawAccount(account) {
  byId("account-title").textContent = account.username || t("profile.addUsername"); // username, never the old full name
  byId("account-avatar").textContent = (account.username || "🙂").trim().charAt(0).toUpperCase();
  byId("account-handle").textContent = account.email || formatPhone(account.phone) || ""; // under the username
  showAccountValue("username", account.username, "profile.addUsername");
  showAccountValue("email", account.email, "profile.notAdded");
  showAccountValue("phone", formatPhone(account.phone), "profile.notAdded");
  showAccountValue("occupation", account.occupation, "profile.notAdded");
  // "Add" instead of "Edit" when there is nothing yet
  ["username", "email", "phone", "occupation"].forEach((field) => {
    setText(byId("edit-" + field), account[field] ? "common.edit" : "profile.add");
  });
}

// "+23051234567" → "+230 5123 4567" (easier to read; saved without spaces)
function formatPhone(phone) {
  return phone ? phone.replace(/^\+230(\d{3,4})(\d{4})$/, "+230 $1 $2") : phone;
}

function showAccountValue(field, value, emptyKey) {
  const element = byId("value-" + field);
  element.textContent = value || t(emptyKey);
  element.classList.toggle("muted", !value);
}

// "Money in: Shared / Not shared 🔒", same provided / none / missing states as everywhere else
function drawShares(shares) {
  [["income", "share-income"], ["loans", "share-loans"]].forEach(([topic, id]) => {
    const state = shares[topic];
    byId(id).textContent = t("profile.share." + state);
    byId(id + "-add").hidden = state !== "missing";
  });
}

// Opens one inline editor (and closes the others). The input starts with the current value.
function openAccountEditor(field) {
  ACCOUNT_FIELDS.forEach((name) => closeAccountEditor(name));
  const form = byId("form-" + field);
  form.hidden = false;
  byId("edit-" + field).setAttribute("aria-expanded", "true");
  byId("error-" + field).textContent = "";
  const values = { username: profileData.username, email: profileData.email,
    phone: profileData.phone, occupation: profileData.occupation };
  const input = byId("input-" + field);
  input.value = values[field] || "";
  form.querySelectorAll('input[type="password"], input[data-was-password]').forEach((box) => { box.value = ""; });
  input.focus();
}

function closeAccountEditor(field) {
  const form = byId("form-" + field);
  if (form.hidden) return;
  form.hidden = true;
  byId("edit-" + field).setAttribute("aria-expanded", "false");
}

// What each Save sends (the server checks everything again and answers with the whole profile)
function sendAccountField(field) {
  const value = byId("input-" + field).value.trim();
  if (field === "username") return saveProfileUsername(value);
  if (field === "email") return saveProfileEmail(value || null, byId("input-email-password").value);
  if (field === "phone") return saveProfilePhone(value || null, byId("input-phone-password").value);
  return saveProfileOccupation(value || null);
}

// Quick checks so the user gets an answer at once (same rules as the backend)
function findAccountProblem(field) {
  const value = byId("input-" + field).value.trim();
  if (field === "username" && !/^[a-zA-Z0-9._-]{3,30}$/.test(value)) return t("error.INVALID_USERNAME");
  if (field === "phone" && value && !/^(\+230)?(5\d{7}|\d{7})$/.test(value.replace(/[\s-]/g, ""))) {
    return t("error.INVALID_PHONE");
  }
  if ((field === "email" || field === "phone") && !byId("input-" + field + "-password").value) {
    return t("profile.needPassword");
  }
  return "";
}

async function saveAccountField(event, field) {
  event.preventDefault();
  const problem = findAccountProblem(field);
  if (problem) {
    byId("error-" + field).textContent = problem;
    return;
  }
  const button = byId("save-" + field);
  button.disabled = true;
  setText(button, "common.saving");
  try {
    await sendAccountField(field);
    profileData = await getProfile(); // show what the server really saved
    closeAccountEditor(field);
    drawAccount(profileData);
    showToast(t("profile.saved"));
  } catch (error) {
    byId("error-" + field).textContent = error.message; // translated by api.js (error.<CODE>)
  } finally {
    button.disabled = false;
    setText(button, "common.save");
  }
}

// The occupation suggestions (the user can also type their own)
function fillOccupationList() {
  const list = byId("occupation-options");
  list.replaceChildren();
  OCCUPATION_KEYS.forEach((key) => {
    const option = document.createElement("option");
    option.value = t(key);
    list.append(option);
  });
}

// ===== CHANGE PASSWORD (pop-up) =====
function openPasswordSheet() {
  byId("password-form").reset();
  byId("pw-error").textContent = "";
  updateNewPasswordRules();
  openSheet("sheet-password");
  byId("pw-current").focus();
}

function updateNewPasswordRules() {
  const password = byId("pw-new").value;
  let passed = 0;
  NEW_PASSWORD_RULES.forEach((rule) => {
    const ok = rule.test(password);
    byId(rule.id).classList.toggle("ok", ok);
    if (ok) passed++;
  });
  return passed === NEW_PASSWORD_RULES.length;
}

async function savePasswordForm(event) {
  event.preventDefault();
  const current = byId("pw-current").value;
  const fresh = byId("pw-new").value;
  if (!current) return showFormError("pw-error", t("profile.needPassword"));
  if (!updateNewPasswordRules()) return showFormError("pw-error", t("error.PASSWORD_WEAK"));
  if (fresh !== byId("pw-confirm").value) return showFormError("pw-error", t("error.PASSWORDS_DIFFERENT"));
  const button = byId("pw-save");
  button.disabled = true;
  setText(button, "common.saving");
  try {
    await changeMyPassword(current, fresh, byId("pw-confirm").value);
    closeSheet("sheet-password");
    showToast(t("profile.passwordChanged"));
  } catch (error) {
    showFormError("pw-error", error.message);
  } finally {
    button.disabled = false;
    setText(button, "profile.changePassword");
  }
}

// Show / Hide buttons next to password boxes: each one only changes ITS input
function setUpPasswordToggles() {
  document.querySelectorAll("[data-show-for]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = byId(button.dataset.showFor);
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      input.toggleAttribute("data-was-password", !showing);
      setText(button, showing ? "login.show" : "login.hide");
      button.dataset.i18nAria = showing ? "login.showPassword" : "login.hidePassword";
      button.setAttribute("aria-label", t(button.dataset.i18nAria));
    });
  });
}

// ===== b) WEEKLY BUDGET + BADGES (moved from the Dashboard, same design and rules) =====
function drawWeekly(weekly, recentWeeks) {
  fillWeeklyInput(weekly);
  drawWeeklySuggestion();
  byId("dash-week-remove").hidden = !weekly.available;
  byId("dash-week-body").hidden = !weekly.available;
  byId("dash-week-note").textContent = weekly.available ? "" : t("dash.week.setOne");
  if (!weekly.available) return;
  const bar = byId("dash-week-bar");
  bar.style.width = Math.min(weekly.percent, 100) + "%";
  bar.parentElement.classList.toggle("over", weekly.state === "over");
  byId("dash-week-text").textContent = t(weekly.state === "over" ? "dash.week.over" : "dash.week.left", {
    spent: formatMoney(weekly.spent), budget: formatMoney(weekly.budget), left: formatMoney(Math.abs(weekly.left)) });
  // "1 day left" / "2 days left" + the badge rule with how many days are recorded so far
  const recorded = weekly.days_recorded;
  byId("dash-week-days").textContent = tPlural("dash.week.daysLeft", weekly.days_left) + " · " +
    (recorded >= weekly.min_tracked_days ? tPlural("dash.week.badgeReady", recorded)
      : t("dash.week.badgeProgress", { min: weekly.min_tracked_days, count: recorded }));
  const list = byId("dash-week-history");
  list.replaceChildren();
  recentWeeks.slice().reverse().forEach((week) => {
    const result = week.kept ? "dash.week.kept" : week.tracked ? "dash.week.missed" : "dash.week.notTracked";
    list.append(makeElement("li", "", formatShortDate(week.week_start) + " – " + formatShortDate(week.week_end) + ": " +
      t(result, { spent: formatMoney(week.spent) })));
  });
}

// ===== WEEKLY BUDGET: SUGGESTION =====
function getSuggestedAmount() {
  const suggestion = weeklyData && weeklyData.weekly_suggestion;
  const amount = suggestion && suggestion.available ? Number(suggestion.amount) : NaN;
  return amount > 0 ? amount : null; // null = nothing to suggest (never NaN in the field)
}

// Saved value → shown; nothing saved → the suggestion. Never overwrites what the user typed.
function fillWeeklyInput(weekly) {
  if (weekInputTyped) return;
  const suggested = getSuggestedAmount();
  byId("dash-week-input").value = weekly.budget !== null ? weekly.budget : suggested !== null ? suggested : "";
}

// "Suggested from …" note, the maths line, and "Use suggested: Rs X" when the field holds another number
function drawWeeklySuggestion() {
  const suggestion = weeklyData && weeklyData.weekly_suggestion;
  const note = byId("dash-week-suggest");
  const math = byId("dash-week-suggest-math");
  const use = byId("dash-week-use");
  note.hidden = math.hidden = use.hidden = true;
  if (!suggestion) return;
  if (suggestion.too_low) {
    note.textContent = t("dash.week.suggest.tooLow");
    note.hidden = false;
    return;
  }
  const amount = getSuggestedAmount();
  if (amount === null) return;
  const p = suggestion.params;
  const weeks = new Intl.NumberFormat(I18n.getLocale(), { maximumFractionDigits: 1 }).format(suggestion.weeks || 0);
  math.textContent = suggestion.source === "budgets"
    ? t("dash.week.suggest.mathBudgets", { monthly: formatMoney(p.monthly), weeks: weeks })
    : t("dash.week.suggest.mathIncome", { income: formatMoney(p.income), bills: formatMoney(p.bills),
      loans: formatMoney(p.loans), saving: formatMoney(p.saving), monthly: formatMoney(p.monthly), weeks: weeks });
  math.hidden = false;
  const saved = weeklyData.weekly.budget;
  if (saved === null && !weekInputTyped) {
    note.textContent = t(suggestion.source === "budgets" ? "dash.week.suggest.budgets" : "dash.week.suggest.income");
    note.hidden = false;
  }
  if (Number(byId("dash-week-input").value) !== amount) {
    use.textContent = t("dash.week.suggest.use", { amount: formatMoney(amount) });
    use.hidden = false;
  }
}

// "Use suggested": fills the field only; the user still taps Save
function useSuggestedWeekly() {
  const amount = getSuggestedAmount();
  if (amount === null) return;
  byId("dash-week-input").value = amount;
  weekInputTyped = true; // their choice now: a reload must not change it
  drawWeeklySuggestion();
  byId("dash-week-input").focus();
}

function drawBadges(badges) {
  const earned = {};
  badges.earned.forEach((badge) => { earned[badge.code] = badge.earned_on; });
  const list = byId("dash-badges");
  list.replaceChildren();
  badges.all.forEach((code) => {
    const li = makeElement("li", "badge" + (earned[code] ? " earned" : ""));
    li.append(makeElement("span", "badge-icon", earned[code] ? BADGE_ICONS[code] : "🔒"),
      makeElement("span", "item-name", t("dash.badge." + code + ".name")),
      makeElement("span", "item-sub", t("dash.badge." + code + ".desc")),
      makeElement("span", "item-sub", earned[code] ? t("dash.badge.earnedOn", { date: formatShortDate(earned[code]) })
        : t("dash.badge.notYet")));
    list.append(li);
  });
}

async function saveWeeklyBudget(event) {
  event.preventDefault();
  const text = byId("dash-week-input").value;
  const amount = Number(text);
  if (text === "" || !(amount > 0) || amount > 10000000) { // same rule as the backend (more than 0, at most 1 crore)
    byId("dash-week-error").textContent = t("dash.week.bad");
    return;
  }
  await sendWeeklyBudget(amount);
}

async function sendWeeklyBudget(amount) {
  byId("dash-week-error").textContent = "";
  try {
    weeklyData = await setWeeklyBudget(amount, getTodayText());
    weekInputTyped = false; // saved / removed: show the saved value (or the suggestion again)
    drawWeekly(weeklyData.weekly, weeklyData.recent_weeks);
    drawBadges(weeklyData.badges);
    announceNewBadges(weeklyData.badges.new);
    showToast(t(amount === null ? "dash.week.removed" : "dash.week.saved"));
  } catch (error) {
    byId("dash-week-error").textContent = error.message;
  }
}

// ===== d) SETTINGS POP-UP: THEME (buttons are in #sheet-settings) =====
function drawThemeButtons() {
  const theme = getTheme(); // theme.js
  [["theme-brighter", "brighter"], ["theme-darker", "darker"]].forEach(([id, name]) => {
    byId(id).classList.toggle("active", theme === name);
    byId(id).setAttribute("aria-pressed", theme === name);
  });
}

function pickTheme(name) {
  setTheme(name); // theme.js: saves it and sets <html data-theme>
  drawThemeButtons();
}

// ===== LANGUAGE SWITCH (called by app.js) =====
function redrawProfile() {
  fillOccupationList();
  drawProfile();
  redrawArcade(); // arcade-tab.js
}

// ===== START (called by app.js once you're logged in) =====
function startProfileTab() {
  ACCOUNT_FIELDS.forEach((field) => {
    byId("edit-" + field).addEventListener("click", () => openAccountEditor(field));
    byId("form-" + field).addEventListener("submit", (event) => saveAccountField(event, field));
    byId("form-" + field).querySelector("[data-cancel]").addEventListener("click", () => {
      closeAccountEditor(field);
      byId("edit-" + field).focus();
    });
  });
  byId("edit-password").addEventListener("click", openPasswordSheet);
  byId("password-form").addEventListener("submit", savePasswordForm);
  byId("pw-new").addEventListener("input", updateNewPasswordRules);
  setUpPasswordToggles();
  byId("share-income-add").addEventListener("click", () => {
    openPage("money");
    showMoneyView("in");
  });
  byId("share-loans-add").addEventListener("click", () => openPage("loans"));
  byId("dash-week-form").addEventListener("submit", saveWeeklyBudget);
  byId("dash-week-remove").addEventListener("click", () => sendWeeklyBudget(null));
  byId("dash-week-use").addEventListener("click", useSuggestedWeekly);
  byId("dash-week-input").addEventListener("input", () => {
    weekInputTyped = true; // the user's own number from now on
    if (weeklyData) drawWeeklySuggestion();
  });
  byId("theme-brighter").addEventListener("click", () => pickTheme("brighter"));
  byId("theme-darker").addEventListener("click", () => pickTheme("darker"));
  fillOccupationList();
  drawThemeButtons();
}
