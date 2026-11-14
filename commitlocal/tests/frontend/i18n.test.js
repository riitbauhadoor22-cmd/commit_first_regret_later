// i18n.test.js — checks the language files (frontend/lang/*.json) and the t() helper in frontend/i18n.js.
// Run: node --test tests/frontend
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const I18n = require("../../frontend/i18n.js");

// ===== LOAD THE FILES =====
const FRONTEND = path.join(__dirname, "..", "..", "frontend");
const BACKEND = path.join(__dirname, "..", "..", "backend");
const readJson = (code) => JSON.parse(fs.readFileSync(path.join(FRONTEND, "lang", code + ".json"), "utf8"));
const dictionaries = { en: readJson("en"), fr: readJson("fr"), mfe: readJson("mfe") };
const en = dictionaries.en;
const enKeys = Object.keys(en).sort();

// {name} placeholders in a text, sorted
const placeholders = (text) => (text.match(/\{\w+\}/g) || []).sort();

// ===== SAME KEYS, NO EMPTY VALUES =====
for (const code of ["en", "fr", "mfe"]) {
  test(code + ".json has exactly the same keys as en.json", () => {
    const keys = Object.keys(dictionaries[code]).sort();
    assert.deepEqual(keys.filter((k) => !(k in en)), [], "extra keys");
    assert.deepEqual(enKeys.filter((k) => !(k in dictionaries[code])), [], "missing keys");
  });

  test(code + ".json has no empty values and keeps every {placeholder}", () => {
    for (const [key, text] of Object.entries(dictionaries[code])) {
      assert.equal(typeof text, "string", key);
      assert.ok(text.trim() !== "", key + " is empty");
      assert.deepEqual(placeholders(text), placeholders(en[key]), key + " placeholders differ from English");
    }
  });
}

// ===== t() =====
test("t() falls back to English and never returns undefined or the raw key", () => {
  I18n.useDictionaries({ en: { "a.only": "English only", "a.both": "Both" }, fr: { "a.both": "Les deux", "a.empty": "" } }, "fr");
  assert.equal(I18n.t("a.both"), "Les deux");
  assert.equal(I18n.t("a.only"), "English only"); // missing in French → English
  assert.equal(I18n.t("a.empty"), "");             // empty French and no English → "" (not the key)
  assert.equal(I18n.t("no.such.key"), "");
  assert.notEqual(I18n.t("no.such.key"), undefined);
});

test("t() fills {placeholders}", () => {
  I18n.useDictionaries(dictionaries, "en");
  assert.equal(I18n.t("toast.added", { name: "Lunch" }), "Added Lunch");
  assert.equal(I18n.t("common.amountOf", { a: "Rs 1", b: "Rs 2" }), "Rs 1 of Rs 2");
  I18n.useDictionaries(dictionaries, "mfe");
  assert.equal(I18n.t("common.perMonth", { amount: "Rs 500" }), "Rs 500 par mwa");
});

test("categories and income types are translated for display only", () => {
  I18n.useDictionaries(dictionaries, "fr");
  assert.equal(I18n.tCategory("Groceries"), "Courses");
  assert.equal(I18n.tCategory("Something new"), "Something new"); // unknown value shown as it is
  assert.equal(I18n.tIncomeType("Salary"), "Salaire");
  I18n.useDictionaries(dictionaries, "en");
});

// ===== EVERY KEY USED IN THE CODE EXISTS =====
test("every data-i18n key in index.html and login.html exists in en.json", () => {
  for (const file of ["index.html", "login.html"]) {
    const html = fs.readFileSync(path.join(FRONTEND, file), "utf8").replace(/<!--[\s\S]*?-->/g, ""); // skip comments
    const keys = [...html.matchAll(/data-i18n(?:-placeholder|-aria)?="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(keys.length > 10, file + " has data-i18n keys");
    for (const key of keys) assert.ok(key in en, file + ": missing key " + key);
  }
});

test("every literal key used in the JS files exists in en.json", () => {
  const namespaces = new Set(enKeys.map((k) => k.split(".")[0]));
  const files = fs.readdirSync(FRONTEND).filter((f) => f.endsWith(".js"));
  let found = 0;
  for (const file of files) {
    const js = fs.readFileSync(path.join(FRONTEND, file), "utf8");
    for (const [, key] of js.matchAll(/"([a-z][A-Za-z]*\.[A-Za-z0-9_.]*[A-Za-z0-9_])"/g)) {
      if (!namespaces.has(key.split(".")[0]) || /\.(js|json|html|css|png)$/.test(key)) continue; // file names
      found++;
      const isPluralBase = key + ".one" in en && key + ".other" in en; // tPlural("base", n) uses base.one / base.other
      assert.ok(key in en || isPluralBase, file + ": missing key " + key);
    }
  }
  assert.ok(found > 100, "found the keys");
});

// ===== PLURALS (tPlural: "<base>.one" + "<base>.other") =====
test("every plural .one key has its .other", () => {  // ("category.other" etc. are normal keys, not plurals)
  for (const key of enKeys.filter((k) => k.endsWith(".one"))) {
    const base = key.slice(0, -4);
    assert.ok(base + ".one" in en && base + ".other" in en, base + " needs .one and .other");
  }
});

test("tPlural picks singular / plural per language", () => {
  I18n.useDictionaries(dictionaries, "en");
  assert.equal(I18n.tPlural("dash.week.daysLeft", 1), "1 day left this week");
  assert.equal(I18n.tPlural("dash.week.daysLeft", 2), "2 days left this week");
  assert.equal(I18n.tPlural("dash.week.daysLeft", 0), "0 days left this week");
  I18n.useDictionaries(dictionaries, "fr");
  assert.equal(I18n.tPlural("dash.week.daysLeft", 0), "0 jour restant cette semaine"); // French: 0 is singular
  assert.equal(I18n.tPlural("dash.week.daysLeft", 3), "3 jours restants cette semaine");
  I18n.useDictionaries(dictionaries, "mfe");
  assert.equal(I18n.tPlural("dash.week.daysLeft", 2), "2 zour reste sa semenn-la");
  assert.ok(!/NaN|undefined/.test(I18n.tPlural("dash.week.daysLeft", undefined)));
  I18n.useDictionaries(dictionaries, "en");
});

test("keys built from codes exist (loan errors, verdicts, category maps)", () => {
  for (const code of ["required", "notNumber", "negative", "zero", "tooBig", "notWhole"]) assert.ok("loan.error." + code in en, code);
  for (const level of ["good", "warn", "over"]) assert.ok("loan.verdict." + level in en, level);
  for (const code of ["income", "budgets", "tooLow"]) assert.ok("dash.week.suggest." + code in en, code); // weekly_suggestion
  for (const key of Object.values(I18n.CATEGORY_KEYS).concat(Object.values(I18n.INCOME_TYPE_KEYS))) assert.ok(key in en, key);
});

test("every error code the backend sends has a translation", () => {
  const sources = [path.join(BACKEND, "errors.py")].concat(
    fs.readdirSync(path.join(BACKEND, "routes")).filter((f) => f.endsWith(".py")).map((f) => path.join(BACKEND, "routes", f)),
    fs.readdirSync(path.join(BACKEND, "game")).filter((f) => f.endsWith(".py")).map((f) => path.join(BACKEND, "game", f)));
  const codes = new Set();
  for (const file of sources) {
    const py = fs.readFileSync(file, "utf8");
    for (const [, code] of py.matchAll(/AppError\(\d+, "([A-Z_]+)"/g)) codes.add(code);
    for (const [, code] of py.matchAll(/: "((?:INVALID|MISSING)_[A-Z_]+)"/g)) codes.add(code);
    for (const [, code] of py.matchAll(/return "((?:INVALID|MISSING)_[A-Z_]+)"/g)) codes.add(code);
  }
  assert.ok(codes.size > 20, "found the backend codes");
  for (const code of codes) assert.ok("error." + code in en, "missing error." + code);
});

// ===== SHARED MONEY FORMATTER =====
test("formatMoney: groups of 3, en 'Rs 100,000', fr/mfe 'Rs 100 000', never NaN", () => {
  assert.equal(I18n.formatMoney(100000, null, "en"), "Rs 100,000");
  assert.equal(I18n.formatMoney(100000, null, "fr").replace(/\u00a0/g, " "), "Rs 100 000");
  assert.equal(I18n.formatMoney(100000, null, "mfe").replace(/\u00a0/g, " "), "Rs 100 000");
  assert.equal(I18n.formatMoney(1234.5, null, "en"), "Rs 1,234.50");
  assert.equal(I18n.formatMoney(1234.5, null, "fr").replace(/\u00a0/g, " "), "Rs 1 234,50");
  assert.equal(I18n.formatMoney(999.6, { whole: true }, "en"), "Rs 1,000");
  for (const bad of [NaN, Infinity, undefined, null, "abc"]) assert.equal(I18n.formatMoney(bad, null, "en"), "Rs 0");
});
