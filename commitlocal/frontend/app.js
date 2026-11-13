// app.js — runs the app page: checks you're logged in, switches tabs, opens and closes the pop-up
// screens, shows short messages ("toasts"), formats money and dates, and turns on offline mode.
// Tabs: Money, Targets, Loans, Arcade. Pop-ups close only on Cancel/Close, after a save, or a tap on the dark area.

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
function openSheet(id) {
  byId(id).hidden = false;
  document.body.style.overflow = "hidden"; // stop the page behind from scrolling
}

function closeSheet(id) {
  byId(id).hidden = true;
  if (!document.querySelector(".sheet:not([hidden])")) {
    document.body.style.overflow = "";
  }
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
const PAGES = ["money", "targets", "loans", "arcade"];

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

  // Fresh numbers every time a tab is opened (adding money in Targets changes Money's "Saved", and so on)
  if (name === "money") loadMoneyTab();     // in money-tab.js
  if (name === "targets") loadTargetsTab(); // in targets-tab.js
  if (name === "loans") prefillLoanFromMoney(); // in loans-tab.js
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
    // The account's saved language wins over this browser's, so the choice follows the user to other devices
    if (me.language && me.language !== I18n.getLanguage()) await setLanguage(me.language);
    window.addEventListener("i18n:change", saveLanguageToAccount); // only after the server's choice is applied
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}

async function logOutAndLeave() {
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
  if (openName === "money") redrawMoneyTab(); // in money-tab.js
  if (openName === "targets") loadTargetsTab();
  if (openName === "loans") redrawLoans(); // in loans-tab.js
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
    button.addEventListener("click", logOutAndLeave);
  });
  registerServiceWorker();
  if (await checkLogin()) {
    startMoneyTab();   // in money-tab.js
    startTargetsTab(); // in targets-tab.js
  }
}

// Runs once every script on the page has loaded
document.addEventListener("DOMContentLoaded", startApp);
