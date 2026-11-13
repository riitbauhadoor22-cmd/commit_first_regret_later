// app.js — runs the app page: checks you're logged in, switches tabs, opens and closes the pop-up
// screens, shows short messages ("toasts"), formats money and dates, and turns on offline mode.
// (This file replaced home.js.)

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

// "2026-11" -> "November 2026"
function formatMonthName(monthText) {
  const [year, month] = monthText.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

// "2026-11-13" -> "13 Nov"
function formatShortDate(dateText) {
  const [year, month, day] = dateText.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
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
    // Tapping the dark area outside the box closes it too
    sheet.addEventListener("click", (event) => {
      if (event.target === sheet) closeSheet(sheet.id);
    });
  });
  document.addEventListener("keydown", (event) => {
    const open = document.querySelectorAll(".sheet:not([hidden])");
    if (event.key === "Escape" && open.length > 0) closeSheet(open[open.length - 1].id);
  });
}

// ===== TABS =====
const PAGES = ["money", "targets", "arcade"];

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
}

function setUpTabs() {
  document.querySelectorAll(".tabbar button").forEach((button) => {
    button.addEventListener("click", () => openPage(button.dataset.page));
  });
}

// ===== LOGIN / LOGOUT =====
async function checkLogin() {
  try {
    await getMe(); // goes to login.html by itself if not logged in
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
