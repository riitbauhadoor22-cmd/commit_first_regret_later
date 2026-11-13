// smoke.test.js — static checks of the frontend without a browser: script order, every called function is defined,
// every element id used in JS exists in the HTML, PWA manifest + service worker files, no API keys, .gitignore.
// Run: node --test tests/frontend
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const FRONTEND = path.join(ROOT, "frontend");
const read = (file) => fs.readFileSync(path.join(FRONTEND, file), "utf8");
const BROWSER = new Set(("if for while switch catch function return typeof await async new Promise Error Number String " +
  "Boolean Array Object Math JSON Date Intl Set Map parseFloat parseInt isNaN isFinite setTimeout clearTimeout " +
  "setInterval clearInterval fetch alert confirm requestAnimationFrame encodeURIComponent decodeURIComponent Chart " +
  "structuredClone super require CustomEvent URL URLSearchParams FormData").split(" "));

function scriptsOf(page) {
  return [...read(page).matchAll(/<script src="([^"]+)"/g)].map((m) => m[1]).filter((s) => !s.startsWith("http"));
}

// Names a script defines: function names, const/let/var, window.X =, and function/arrow parameters
function definedNames(code) {
  const names = new Set();
  for (const re of [/function\s+([A-Za-z_$][\w$]*)/g, /(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g, /window\.([A-Za-z_$][\w$]*)\s*=/g])
    for (const m of code.matchAll(re)) names.add(m[1]);
  for (const m of code.matchAll(/(?:const|let|var)\s*\{([^}]+)\}/g)) m[1].split(",").forEach((s) => names.add(s.split(":").pop().trim()));
  for (const m of code.matchAll(/\(([\w$,\s=]*)\)\s*=>|function\s*[\w$]*\s*\(([\w$,\s=]*)\)/g))
    (m[1] || m[2] || "").split(",").forEach((s) => names.add(s.split("=")[0].trim()));
  return names;
}

// ===== SCRIPT ORDER =====
test("index.html loads i18n first and each helper before the file that uses it", () => {  // order matters for plain scripts
  const s = scriptsOf("index.html");
  assert.equal(s[0], "i18n.js");
  const before = (a, b) => assert.ok(s.indexOf(a) >= 0 && s.indexOf(a) < s.indexOf(b), a + " must load before " + b);
  before("api.js", "app.js");
  before("app.js", "money-tab.js");
  before("budget-calc.js", "money-tab.js");
  before("loan-calc.js", "loans-tab.js");
  const html = read("index.html");
  assert.ok(html.indexOf("chart.umd") < html.indexOf('src="loans-tab.js"'), "Chart.js must load before loans-tab.js");
});

test("login.html loads i18n.js before login.js", () => {  // login page order
  assert.deepEqual(scriptsOf("login.html"), ["i18n.js", "login.js"]);
});

test("every script file used by the pages exists and is cached by the service worker", () => {  // offline needs them
  const sw = read("service-worker.js");
  for (const file of new Set([...scriptsOf("index.html"), ...scriptsOf("login.html")])) {
    assert.ok(fs.existsSync(path.join(FRONTEND, file)), file + " is missing");
    assert.ok(sw.includes('"' + file + '"'), file + " is not in service-worker.js APP_FILES");
  }
});

// ===== FUNCTIONS AND IDS =====
for (const page of ["index.html", "login.html"]) {
  const files = scriptsOf(page);
  const allCode = files.map(read).join("\n");
  const defined = definedNames(allCode);

  test(page + ": every function called in its scripts is defined (no 'getMe is not defined')", () => {
    const missing = [];
    for (const file of files) {
      const code = read(file).replace(/\/\/.*$/gm, "").replace(/"[^"\n]*"|'[^'\n]*'/g, '""');
      for (const m of code.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/g)) {
        if (!defined.has(m[2]) && !BROWSER.has(m[2]) && m[2] !== "preventDefault") missing.push(file + ": " + m[2]);
      }
    }
    assert.deepEqual([...new Set(missing)], []);
  });

  test(page + ": every element id used in JS exists in the HTML", () => {
    const ids = new Set([...read(page).matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
    const missing = [];
    for (const file of files) {
      const re = /(?:getElementById|byId|openSheet|closeSheet)\(\s*["']([\w-]+)["']\s*[,)]|querySelector(?:All)?\(\s*["']#([\w-]+)/g;
      for (const m of read(file).matchAll(re)) if (!ids.has(m[1] || m[2])) missing.push(file + ": #" + (m[1] || m[2]));
    }
    assert.deepEqual(missing, []);
  });
}

test("every tab page in PAGES (app.js) has a page-<name> element", () => {  // byId("page-" + name)
  const pages = JSON.parse(read("app.js").match(/const PAGES = (\[[^\]]*\])/)[1]);
  for (const name of pages) assert.ok(read("index.html").includes('id="page-' + name + '"'), "page-" + name);
});

// ===== PWA =====
test("manifest.json has name, short_name, start_url, display, theme_color and 192 + 512 icons that exist", () => {
  const manifest = JSON.parse(read("manifest.json"));
  for (const key of ["name", "short_name", "start_url", "display", "theme_color"]) assert.ok(manifest[key], key);
  for (const size of ["192x192", "512x512"]) {
    const icon = manifest.icons.find((i) => i.sizes === size);
    assert.ok(icon && fs.existsSync(path.join(FRONTEND, icon.src)), size + " icon");
  }
});

test("both pages link the manifest and app.js registers the service worker", () => {
  assert.ok(read("index.html").includes('rel="manifest"'));
  assert.ok(read("app.js").includes("serviceWorker.register"));
});

// ===== SECURITY =====
test("no API keys or secrets in any frontend file", () => {  // keys must stay in backend/.env
  const keyLike = /(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|(api[_-]?key|secret|app_password)\s*[:=]\s*["'][^"']{8,})/i;
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
  for (const file of walk(FRONTEND).filter((f) => /\.(js|html|json|css)$/.test(f))) {
    assert.ok(!keyLike.test(fs.readFileSync(file, "utf8")), "key-like text in " + file);
  }
});

test(".env and venv are git-ignored and .env.example has no real values", () => {
  const ignore = fs.readFileSync(path.join(ROOT, ".gitignore"), "utf8").split(/\r?\n/).map((l) => l.trim());
  assert.ok(ignore.includes(".env") && ignore.includes("venv/"));
  const example = fs.readFileSync(path.join(ROOT, "backend", ".env.example"), "utf8");
  for (const line of example.split(/\r?\n/).filter((l) => /^(GMAIL_APP_PASSWORD|OPENAI_API_KEY)=/.test(l))) {
    assert.equal(line.split("=")[1].trim(), "", line.split("=")[0] + " must be empty in .env.example");
  }
});
