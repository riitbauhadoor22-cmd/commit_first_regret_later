// login.js — runs login.html: tabs, the live password strength meter, and the calls to /api/auth/...

// ===== STATE =====
let currentEmail = ""; // remembered between the password step and the code step

// Same rules as get_password_problems() in backend/security.py
const PASSWORD_RULES = [
  { id: "rule-length", test: (p) => p.length >= 8 },
  { id: "rule-upper", test: (p) => /[A-Z]/.test(p) },
  { id: "rule-lower", test: (p) => /[a-z]/.test(p) },
  { id: "rule-number", test: (p) => /[0-9]/.test(p) },
  { id: "rule-symbol", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

// Index = how many rules pass (0 to 5)
const STRENGTH_LEVELS = [
  { label: "", color: "#ddd" },
  { label: "Very weak", color: "#d32f2f" },
  { label: "Weak", color: "#f57c00" },
  { label: "Okay", color: "#fbc02d" },
  { label: "Good", color: "#7cb342" },
  { label: "Strong", color: "#2e7d32" },
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
    return { ok: res.ok, status: res.status, message: readMessage(body) };
  } catch (error) {
    return { ok: false, status: 0, message: "No connection. Check your internet and try again." };
  }
}

function readMessage(body) {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return "Please check: " + body.detail.map((d) => d.msg).join(", "); // FastAPI form errors
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
  byId("meter-label").textContent = level.label;
  byId("meter-label").style.color = level.color;
}

// ===== FORM ACTIONS =====
async function registerUser(event) {
  event.preventDefault();
  const password = byId("reg-password").value;
  if (countPassedRules(password) < PASSWORD_RULES.length) {
    return showMessage("Your password doesn't meet all the rules yet.", true);
  }
  if (password !== byId("reg-confirm").value) {
    return showMessage("The two passwords don't match.", true);
  }
  const button = event.submitter;
  button.disabled = true;
  const result = await postJson("/api/auth/register", {
    full_name: byId("reg-name").value,
    email: byId("reg-email").value,
    password: password,
    confirm_password: byId("reg-confirm").value,
  });
  button.disabled = false;
  if (!result.ok) return showMessage(result.message, true);

  byId("login-email").value = byId("reg-email").value;
  byId("register-form").reset();
  updateStrengthMeter();
  openTab("login");
  showMessage(result.message, false);
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
    showOnly("code-form");
    byId("code-input").focus();
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
  showOnly("code-form");
  byId("code-input").focus();
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
  if (!result.ok) return showMessage(result.message, true);
  window.location.href = "index.html";
}

// ===== START =====
byId("tab-login").addEventListener("click", () => openTab("login"));
byId("tab-register").addEventListener("click", () => openTab("register"));
byId("reg-password").addEventListener("input", updateStrengthMeter);
byId("register-form").addEventListener("submit", registerUser);
byId("login-form").addEventListener("submit", loginUser);
byId("code-form").addEventListener("submit", verifyCode);
byId("send-code-btn").addEventListener("click", sendLoginCode);

// Already logged in? Go straight to the app
fetch("/api/auth/me").then((res) => {
  if (res.ok) window.location.href = "index.html";
});
