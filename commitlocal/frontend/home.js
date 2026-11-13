// home.js — runs index.html: sends you to the login page if you're not logged in, shows your name, logs you out.

// ===== API CALL =====
async function loadUser() {
  const res = await fetch("/api/auth/me");
  if (!res.ok) {
    window.location.href = "login.html"; // not logged in
    return;
  }
  const user = await res.json();
  document.getElementById("greeting").textContent = "Hi, " + user.full_name + "!";
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "login.html";
}

// ===== START =====
document.getElementById("logout-btn").addEventListener("click", logout);
loadUser();
