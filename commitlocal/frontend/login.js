// login.js — runs login.html: tabs, the live password strength meter, the Register checks (username, email and/or
// phone) and the calls to /api/auth/... Login = email OR phone number + password, then a 6-digit code.
// Texts come from i18n.js: t("key"). Backend replies carry a "code" that is translated here (see readMessage).

// ===== STATE =====
let currentEmail = ""; // email or phone, remembered between the password step and the code step
let codeExpiresAt = 0;  // when the current code expires (ms, from Date.now())
let resendReadyAt = 0;  // when "Resend OTP" can be tapped again (ms)
let codeTimer = null;   // the 1-second countdown interval

// Same rules as get_password_problems() in backend/security.py
const PASSWORD_RULES = [
  { id: "rule-length", test: (p) => p.length >= 8 },
  { id: "rule-upper", test: (p) => /[A-Z]/.test(p) },
  { id: "rule-lower", test: (p) => /[a-z]/.test(p) },
  { id: "rule-number", test: (p) => /[0-9]/.test(p) },
  { id: "rule-symbol", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

// Same checks as clean_username() / clean_phone() in backend/models.py (the backend checks again)
const USERNAME_PATTERN = /^[a-zA-Z0-9._-]{3,30}$/;
const PHONE_PATTERN = /^(\+230)?(5\d{7}|\d{7})$/; // Mauritius: mobile 5XXXXXXX or a 7-digit landline

// Index = how many rules pass (0 to 5)
const STRENGTH_LEVELS = [
  { key: "", color: "#3a4670" },
  { key: "login.strength.veryWeak", color: "#ff5c6c" },
  { key: "login.strength.weak", color: "#ff9f43" },
  { key: "login.strength.okay", color: "#ffd24d" },
  { key: "login.strength.good", color: "#9be15d" },
  { key: "login.strength.strong", color: "#45e08a" },
];

// ===== HELPERS =====
function byId(id) {
  return document.getElementById(id);
}

function showMessage(text, isError) {
  byId("message").textContent = text;
  byId("message").className = isError ? "message error" : "message";
}

function showOnly(sectionId) {
  ["login-form", "register-form", "code-form", "locked-box"].forEach((id) => {
    byId(id).hidden = id !== sectionId;
  });
}

// ===== API CALL =====
async function postJson(url, data) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const body = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, message: readMessage(body),
             expiresIn: body.expires_in, resendWait: body.resend_wait };
  } catch (error) {
    return { ok: false, status: 0, message: t("error.OFFLINE") };
  }
}

// The backend's "code" → translated text ("error.<CODE>" for problems, "auth.<CODE>" for good news).
// Unknown code → the backend's English message, so the user always sees something.
function readMessage(body) {
  if (body.code && I18n.hasKey("error." + body.code)) return t("error." + body.code, body.params);
  if (body.code && I18n.hasKey("auth." + body.code)) return t("auth." + body.code, body.params);
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return t("login.pleaseCheck") + " " + body.detail.map((d) => d.msg).join(", "); // FastAPI form errors
  return body.message || "";
}

// ===== TABS =====
function openTab(name) {
  const isLogin = name === "login";
  byId("tab-login").classList.toggle("active", isLogin);
  byId("tab-register").classList.toggle("active", !isLogin);
  byId("tab-login").setAttribute("aria-selected", isLogin);
  byId("tab-register").setAttribute("aria-selected", !isLogin);
  showOnly(isLogin ? "login-form" : "register-form");
  showMessage("");
}

// ===== CODE COUNTDOWN + RESEND =====
// Show the code screen and (re)start the expiry countdown and the resend cooldown
function startCodeScreen(result) {
  showOnly("code-form");
  byId("code-input").value = "";
  byId("code-input").focus();
  codeExpiresAt = Date.now() + (result.expiresIn || 300) * 1000;
  resendReadyAt = Date.now() + (result.resendWait || 30) * 1000;
  clearInterval(codeTimer);
  codeTimer = setInterval(updateCodeTimer, 1000);
  updateCodeTimer();
}

function updateCodeTimer() {
  const secondsLeft = Math.max(0, Math.ceil((codeExpiresAt - Date.now()) / 1000));
  const waitLeft = Math.max(0, Math.ceil((resendReadyAt - Date.now()) / 1000));
  const timer = byId("code-timer");
  if (secondsLeft > 0) {
    const secs = String(secondsLeft % 60).padStart(2, "0"); // 4:05, not 4:5
    timer.textContent = t("login.expiresIn", { time: Math.floor(secondsLeft / 60) + ":" + secs });
    timer.classList.remove("error");
  } else {
    showCodeExpired();
  }
  const resend = byId("resend-btn");
  resend.disabled = waitLeft > 0;
  resend.textContent = waitLeft > 0 ? t("login.resendIn", { n: waitLeft }) : t("login.resend");
}

function showCodeExpired() {
  byId("code-timer").textContent = t("login.codeExpired");
  byId("code-timer").classList.add("error");
  byId("verify-btn").disabled = true; // an expired code can't work, so only Resend is useful
  showMessage("");
}

async function resendCode() {
  if (Date.now() < resendReadyAt) return; // cooldown (the backend checks this too)
  byId("resend-btn").disabled = true;
  const result = await postJson("/api/auth/resend-code", { email: currentEmail });
  if (!result.ok) {
    updateCodeTimer();
    return showMessage(result.message, true);
  }
  byId("verify-btn").disabled = false;
  startCodeScreen(result);
  showMessage(result.message, false);
}

// ===== REGISTER TAB SHOW / HIDE =====
function setRegisterTabVisible(visible) {
  byId("tab-register").hidden = !visible;
  byId("show-register-link").hidden = visible;
}

// ===== SHOW / HIDE PASSWORD =====
// Wraps every password box with a "Show" button so people can check what they typed
function addPasswordToggles() {
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    const wrap = document.createElement("span");
    wrap.className = "password-wrap";
    input.replaceWith(wrap);
    const btn = document.createElement("button");
    btn.type = "button"; // never submits the form
    btn.className = "password-toggle";
    setText(btn, "login.show"); // setText (i18n.js) keeps the key, so a language switch updates it
    btn.dataset.i18nAria = "login.showPassword";
    btn.setAttribute("aria-label", t("login.showPassword"));
    btn.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      setText(btn, showing ? "login.show" : "login.hide");
      btn.dataset.i18nAria = showing ? "login.showPassword" : "login.hidePassword";
      btn.setAttribute("aria-label", t(btn.dataset.i18nAria));
    });
    wrap.append(input, btn);
  });
}

// ===== PASSWORD STRENGTH METER =====
function countPassedRules(password) {
  let passed = 0;
  PASSWORD_RULES.forEach((rule) => {
    const ok = rule.test(password);
    byId(rule.id).classList.toggle("ok", ok);
    if (ok) passed++;
  });
  return passed;
}

function updateStrengthMeter() {
  const passed = countPassedRules(byId("reg-password").value);
  const level = STRENGTH_LEVELS[passed];
  byId("meter-bar").style.width = passed * 20 + "%";
  byId("meter-bar").style.background = level.color;
  byId("meter-label").textContent = level.key ? t(level.key) : "";
  byId("meter-label").style.color = level.color;
}

// ===== FORM ACTIONS =====
// Quick checks of username / email / phone before sending (texts = the backend's error codes)
function findRegisterProblem(username, email, phone) {
  if (!USERNAME_PATTERN.test(username)) return t("error.INVALID_USERNAME");
  if (!email && !phone) return t("error.EMAIL_OR_PHONE_REQUIRED");
  if (phone && !PHONE_PATTERN.test(phone.replace(/[\s-]/g, ""))) return t("error.INVALID_PHONE");
  return "";
}

async function registerUser(event) {
  event.preventDefault();
  const username = byId("reg-username").value.trim();
  const email = byId("reg-email").value.trim();
  const phone = byId("reg-phone").value.trim();
  const problem = findRegisterProblem(username, email, phone);
  if (problem) return showMessage(problem, true);
  const password = byId("reg-password").value;
  if (countPassedRules(password) < PASSWORD_RULES.length) {
    return showMessage(t("login.rulesNotMet"), true);
  }
  if (password !== byId("reg-confirm").value) {
    return showMessage(t("error.PASSWORDS_DIFFERENT"), true);
  }
  const button = event.submitter;
  button.disabled = true;
  const result = await postJson("/api/auth/register", {
    username: username,
    email: email || null, // empty = not given (a phone number is enough)
    phone: phone || null,
    password: password,
    confirm_password: byId("reg-confirm").value,
  });
  button.disabled = false;
  if (!result.ok) return showMessage(result.message, true);

  byId("login-email").value = email || phone; // log in with what they gave

  byId("register-form").reset();
  updateStrengthMeter();
  openTab("login");
  setRegisterTabVisible(false); // they have an account now; the link below the form brings it back
  byId("login-password").focus();
  showMessage(t("login.accountCreated"), false);
}

async function loginUser(event) {
  event.preventDefault();
  currentEmail = byId("login-email").value;
  const button = event.submitter;
  button.disabled = true;
  const result = await postJson("/api/auth/login", {
    email: currentEmail,
    password: byId("login-password").value,
  });
  button.disabled = false;
  byId("login-password").value = "";

  if (result.ok) {
    startCodeScreen(result);
    showMessage(result.message, false);
  } else if (result.status === 423) {
    showOnly("locked-box"); // 423 = account locked
    showMessage(result.message, true);
  } else {
    showMessage(result.message, true);
  }
}

async function sendLoginCode() {
  byId("send-code-btn").disabled = true;
  const result = await postJson("/api/auth/send-login-code", { email: currentEmail });
  byId("send-code-btn").disabled = false;
  if (!result.ok) return showMessage(result.message, true);
  startCodeScreen(result);
  showMessage(result.message, false);
}

async function verifyCode(event) {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const result = await postJson("/api/auth/verify-code", {
    email: currentEmail,
    code: byId("code-input").value.trim(),
  });
  button.disabled = false;
  if (result.status === 410) {
    codeExpiresAt = 0; // backend says expired: show the same message + Resend
    return updateCodeTimer();
  }
  if (!result.ok) return showMessage(result.message, true);
  clearInterval(codeTimer);
  window.location.href = "index.html";
}

// ===== LANGUAGE SWITCH =====
// Static texts update by themselves (data-i18n); redraw the ones made here
function redrawLoginTexts() {
  updateStrengthMeter();
  if (!byId("code-form").hidden) updateCodeTimer();
}

// ===== START =====
async function startLoginPage() {
  await I18n.ready; // wait for the texts (i18n.js) before drawing anything
  window.addEventListener("i18n:change", redrawLoginTexts);
  addPasswordToggles();
  byId("tab-login").addEventListener("click", () => openTab("login"));
  byId("tab-register").addEventListener("click", () => openTab("register"));
  byId("reg-password").addEventListener("input", updateStrengthMeter);
  byId("register-form").addEventListener("submit", registerUser);
  byId("login-form").addEventListener("submit", loginUser);
  byId("code-form").addEventListener("submit", verifyCode);
  byId("send-code-btn").addEventListener("click", sendLoginCode);
  byId("resend-btn").addEventListener("click", resendCode);
  byId("show-register-link").addEventListener("click", () => {
    setRegisterTabVisible(true);
    openTab("register");
  });

  // Already logged in? Go straight to the app
  fetch("/api/auth/me").then((res) => {
    if (res.ok) window.location.href = "index.html";
  });
}

startLoginPage();
