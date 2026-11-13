// api.js — every call to our backend (/api/...) goes through here. Not logged in (401) → back to the login page.

// ===== API CALLS =====
// Returns { ok, status, data, message } and never throws
async function callApi(method, url, body) {
  try {
    const res = await fetch(url, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
      window.location.href = "login.html";
      return { ok: false, status: 401, data: {}, message: "Please log in again." };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data: data, message: apiMessage(data) };
  } catch (error) {
    return { ok: false, status: 0, data: {}, message: "No connection. Check your internet and try again." };
  }
}

function apiMessage(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return "Please check the amount and other fields."; // FastAPI form errors
  return data.message || "";
}
