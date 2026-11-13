// app.js — login check, log out, tab switching, money formatting, and opening/closing pop-ups.

// ===== HELPERS =====
function byId(id) {
  return document.getElementById(id);
}

// 1200 → "Rs 1,200" (Indian digit grouping)
function formatRs(amount) {
  return "Rs " + Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

// Today as YYYY-MM-DD in the phone's own time zone
function todayString() {
  return new Date().toLocaleDateString("en-CA");
}

// ===== POP-UPS =====
// A pop-up closes ONLY from: its X / Cancel buttons ([data-close]), closeModal() after a save,
// or a tap on the dark overlay itself. No blur / focusout / resize handlers, so the phone
// keyboard opening (which resizes the screen) can never close it.
function openModal(id) {
  byId(id).hidden = false;
  document.body.classList.add("no-scroll"); // stop the page behind from scrolling
}

function closeModal(id) {
  byId(id).hidden = true;
  document.body.classList.remove("no-scroll");
}

function setUpModal(id) {
  const overlay = byId(id);
  let pressStartedOnOverlay = false;
  // Remember where the tap/press STARTED. A press that starts in an input and ends on the
  // overlay (e.g. selecting text) must not close the pop-up.
  overlay.addEventListener("pointerdown", (event) => {
    pressStartedOnOverlay = event.target === overlay;
  });
  overlay.addEventListener("click", (event) => {
    // event.target is the overlay only when the dark area itself was tapped, not anything inside the box
    if (event.target === overlay && pressStartedOnOverlay) closeModal(id);
  });
  overlay.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(id));
  });
}

// ===== TABS =====
function openTab(name) {
  ["money", "targets", "arcade"].forEach((tab) => {
    byId("page-" + tab).hidden = tab !== name;
  });
  document.querySelectorAll(".tab-bar-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
}

// ===== LOGIN / LOGOUT =====
async function loadUser() {
  const result = await callApi("GET", "/api/auth/me"); // 401 → login page (in api.js)
  if (result.ok) byId("greeting").textContent = "Hi, " + result.data.full_name + "!";
}

async function logout() {
  await callApi("POST", "/api/auth/logout");
  window.location.href = "login.html";
}

// ===== START =====
document.querySelectorAll("[data-logout]").forEach((b) => b.addEventListener("click", logout));
document.querySelectorAll(".tab-bar-btn").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelectorAll(".overlay").forEach((o) => closeModal(o.id));
});
loadUser();
