// app.js — runs the app page: checks you're logged in, switches tabs, opens and closes the pop-up
// screens, shows short messages ("toasts"), formats money and dates, and turns on offline mode.
// Tabs: Money, Dashboard, Loans, Profile (the Dashboard opens first). Pop-ups close only on Cancel/Close, after a save,
// a tap on the dark area or Esc; focus goes back to the button that opened them. Every "Log out" asks first.

// ===== SMALL HELPERS =====
function byId(id) {
  return document.getElementById(id);
}

// Makes an element with optional class and text. Using textContent keeps user text safe.
function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

// Same, but the text is a translation key: it re-translates by itself when the language changes
function makeTextElement(tag, className, key, params) {
  const element = makeElement(tag, className);
  setText(element, key, params); // in i18n.js
  return element;
}

// 1234.5 -> "Rs 1,234.50"   150000 -> "Rs 1,50,000"
function formatMoney(amount) {
  const hasPaise = Math.round(Math.abs(amount) * 100) % 100 !== 0;
  const text = Math.abs(amount).toLocaleString("en-IN", {
    minimumFractionDigits: hasPaise ? 2 : 0,
    maximumFractionDigits: 2,
  });
  return "Rs " + text;
}

// Income: "+Rs 500" (green). Expense: "−Rs 500" (orange).
function formatIn(amount) { return "+" + formatMoney(amount); }
function formatOut(amount) { return "−" + formatMoney(amount); }

// Today's date on this phone as "YYYY-MM-DD"
function getTodayText() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return now.getFullYear() + "-" + month + "-" + day;
}

function getThisMonthText() {
  return getTodayText().slice(0, 7);
}

// "2026-11" -> "November 2026" / "novembre 2026" (month names in the current language, see i18n.js)
function formatMonthName(monthText) {
  const [year, month] = monthText.split("-").map(Number);
  return I18n.formatDate(new Date(year, month - 1, 1), { month: "long", year: "numeric" });
}

// "2026-11-13" -> "13 Nov" / "13 nov."
function formatShortDate(dateText) {
  const [year, month, day] = dateText.split("-").map(Number);
  return I18n.formatDate(new Date(year, month - 1, day), { day: "numeric", month: "short" });
}

// "2026-11" + 1 -> "2026-12"
function addMonths(monthText, count) {
  const [year, month] = monthText.split("-").map(Number);
  const date = new Date(year, month - 1 + count, 1);
  return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0");
}

// The phone asks for less movement (Settings → Accessibility): no wave, no coin drop, no sliding
function prefersLessMotion() {
  return Boolean(window.matchMedia) && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// ===== OPTIONAL INFORMATION PROMPTS (used by the Money, Savings and Loans views) =====
// Missing → "Add your income…" + [Add] + [No income this month]. "none" → "Marked: …" + [Undo]. Provided → nothing.
// texts = { ask, add, none, marked } translation keys; onAdd = opens the right form (or null); reload redraws the tab.
function makeInfoPrompt(topic, state, texts, month, onAdd, reload) {
  if (state === "provided") return null;
  const box = makeElement("div", "info-prompt");
  const actions = makeElement("div", "info-actions");
  if (state === "missing") {
    box.append(makeElement("p", "", t(texts.ask)));
    if (onAdd) actions.append(makeButton(t(texts.add), "btn btn-small", onAdd));
    actions.append(makeButton(t(texts.none), "link-btn", () => chooseNone(topic, month, true, reload)));
  } else {
    box.append(makeElement("p", "muted", t(texts.marked)));
    actions.append(makeButton(t("common.undo"), "link-btn", () => chooseNone(topic, month, false, reload)));
  }
  box.append(actions);
  return box;
}

function makeButton(text, className, onClick) {
  const button = makeElement("button", className, text);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

async function chooseNone(topic, month, none, reload) {
  try {
    await setInfoChoice(topic, month, none);
    await reload();
  } catch (error) {
    showToast(error.message, true);
  }
}

// ===== TOAST (short message at the bottom) =====
let toastTimer = null;

function showToast(text, isError) {
  const toast = byId("toast");
  toast.textContent = text;
  toast.classList.toggle("error", Boolean(isError));
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2800);
}

// Shows a problem under a form and scrolls to it, so it isn't hidden below the screen
function showFormError(elementId, text) {
  const element = byId(elementId);
  element.textContent = text;
  element.scrollIntoView({ block: "center", behavior: "smooth" });
}

// ===== POP-UP SCREENS ("sheets") =====
const sheetOpeners = {}; // sheet id → the button that opened it (focus goes back there on close)

function openSheet(id) {
  sheetOpeners[id] = document.activeElement;
  byId(id).hidden = false;
  document.body.style.overflow = "hidden"; // stop the page behind from scrolling
}

function closeSheet(id) {
  if (byId(id).hidden) return;
  byId(id).hidden = true;
  if (!document.querySelector(".sheet:not([hidden])")) {
    document.body.style.overflow = "";
  }
  const opener = sheetOpeners[id];
  if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
  sheetOpeners[id] = null;
}

function setUpSheets() {
  document.querySelectorAll(".sheet").forEach((sheet) => {
    // "Cancel" / "Close" buttons
    sheet.querySelectorAll("[data-close]").forEach((button) => {
      button.addEventListener("click", () => closeSheet(sheet.id));
    });
    // Tapping the dark area outside the box closes it too. We remember where the press STARTED:
    // a press that starts in an input and ends on the dark area (e.g. selecting text) must not close it.
    // No blur/resize handlers, so the phone keyboard opening can never close a pop-up.
    let pressStartedOnOverlay = false;
    sheet.addEventListener("pointerdown", (event) => {
      pressStartedOnOverlay = event.target === sheet;
    });
    sheet.addEventListener("click", (event) => {
      if (event.target === sheet && pressStartedOnOverlay) closeSheet(sheet.id);
    });
  });
  document.addEventListener("keydown", (event) => {
    const open = document.querySelectorAll(".sheet:not([hidden])");
    if (event.key === "Escape" && open.length > 0) closeSheet(open[open.length - 1].id);
  });
}

// ===== TABS =====
const PAGES = ["money", "dashboard", "loans", "profile"];

function openPage(name) {
  PAGES.forEach((page) => {
    byId("page-" + page).hidden = page !== name;
  });
  document.querySelectorAll(".tabbar button").forEach((button) => {
    const isActive = button.dataset.page === name;
    button.classList.toggle("active", isActive);
    if (isActive) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);

  // Fresh numbers every time a tab is opened (adding money to a goal changes the Dashboard jar, and so on)
  if (name === "dashboard") loadDashboard(); // in dashboard.js
  if (name === "money") {
    loadMoneyTab(); // in money-tab.js
    if (moneyView === "savings") loadSavingsView(); // in savings-view.js
  }
  if (name === "loans") {
    prefillLoanFromMoney(); // in loans-tab.js
    loadMyLoans();
  }
  if (name === "profile") loadProfileTab(); // in profile-tab.js
}

function setUpTabs() {
  document.querySelectorAll(".tabbar button").forEach((button) => {
    button.addEventListener("click", () => openPage(button.dataset.page));
  });
}

// ===== LOGIN / LOGOUT =====
async function checkLogin() {
  try {
    const me = await getMe(); // goes to login.html by itself if not logged in
    currentUserName = me.full_name || ""; // for the Dashboard welcome (dashboard.js)
    // The account's saved language wins over this browser's, so the choice follows the user to other devices
    if (me.language && me.language !== I18n.getLanguage()) await setLanguage(me.language);
    window.addEventListener("i18n:change", saveLanguageToAccount); // only after the server's choice is applied
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}

// Every "Log out" button first asks "Log out?" (Cancel is focused, so a slip of the finger does nothing)
function askToLogOut() {
  openSheet("sheet-logout");
  byId("logout-cancel").focus();
}

// "Log out" in the pop-up: the server ends the session and clears the cookie, then the login page opens
async function logOutAndLeave() {
  const button = byId("logout-confirm");
  button.disabled = true;
  byId("logout-cancel").disabled = true;
  setText(button, "logout.busy");
  try {
    await logOut();
  } finally {
    window.location.href = "login.html";
  }
}

// ===== LANGUAGE SWITCH =====
// Logged in: also remember the new language on the account. Failures are silent (localStorage still has it).
function saveLanguageToAccount(event) {
  saveMyLanguage(event.detail.language).catch(() => {});
}

// Static texts are re-translated by i18n.js; here we redraw the open tab so JS-made lists, dates and graphs follow
function redrawAfterLanguageChange() {
  const openName = PAGES.find((page) => !byId("page-" + page).hidden);
  if (openName === "dashboard") redrawDashboard(); // in dashboard.js
  if (openName === "money") redrawMoneyTab(); // in money-tab.js
  if (openName === "loans") redrawLoans(); // in loans-tab.js
  if (openName === "profile") redrawProfile(); // in profile-tab.js
}

// ===== OFFLINE (service worker) =====
function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("service-worker.js").catch(() => {
      // Not on https (or not supported): the app still works, just not offline
    });
  }
}

// ===== START =====
async function startApp() {
  await I18n.ready; // nothing is drawn before the texts are loaded
  window.addEventListener("i18n:change", redrawAfterLanguageChange);
  setUpTabs();
  setUpSheets();
  document.querySelectorAll(".logout-btn").forEach((button) => {
    button.addEventListener("click", askToLogOut);
  });
  byId("logout-confirm").addEventListener("click", logOutAndLeave);
  registerServiceWorker();
  if (await checkLogin()) {
    startMoneyTab();    // in money-tab.js
    startSavingsView(); // in savings-view.js (Money → Savings)
    startProfileTab();  // in profile-tab.js
    startDashboard();   // in dashboard.js: the Dashboard is the first page you see after logging in
  }
}

// Runs once every script on the page has loaded
document.addEventListener("DOMContentLoaded", startApp);
