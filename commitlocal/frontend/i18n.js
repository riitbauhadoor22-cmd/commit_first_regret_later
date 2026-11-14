// i18n.js — the app's languages: English (en), French (fr), Mauritian Creole / Kreol Morisien (mfe).
// Texts live in lang/en.json, lang/fr.json, lang/mfe.json. Loaded BEFORE every other script.
// t("money.in") → text in the current language (English if missing, "" if unknown — never the raw key or "undefined").
// HTML: data-i18n="key" (text), data-i18n-placeholder="key", data-i18n-aria="key" (aria-label).
// setLanguage("fr") switches without reloading and fires the "i18n:change" event so pages can redraw.
// Works in the browser (window.I18n, t, setText) and in Node for tests (require("../../frontend/i18n.js")).

(function () {
  // ===== SETTINGS =====
  const LANGUAGES = ["en", "fr", "mfe"];
  const SHORT_NAMES = { en: "EN", fr: "FR", mfe: "KM" }; // labels in the language picker
  const LOCALES = { en: "en-MU", fr: "fr-MU", mfe: "fr-MU" }; // dates; Creole uses French month names
  const STORAGE_KEY = "language";

  // Values the backend sends (and expects back) → display key. The values themselves never change.
  const CATEGORY_KEYS = {
    Groceries: "category.groceries", Transport: "category.transport", Bills: "category.bills",
    Utilities: "category.utilities", "Food & drinks": "category.food", Shopping: "category.shopping",
    Subscriptions: "category.subscriptions", "Fun & outings": "category.fun", Other: "category.other",
  };
  const INCOME_TYPE_KEYS = {
    Salary: "incomeType.salary", Allowance: "incomeType.allowance", "Side hustle": "incomeType.sideHustle",
    Scholarship: "incomeType.scholarship", Other: "incomeType.other",
  };

  // ===== STATE =====
  const dictionaries = {}; // language code → { key: text }
  let current = "en";

  // ===== PICKING THE START LANGUAGE =====
  function readSavedLanguage() {
    try {
      return localStorage.getItem(STORAGE_KEY); // can throw in private mode / blocked storage
    } catch (error) {
      return null;
    }
  }

  function saveLanguage(code) {
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (error) {
      // Storage blocked: the choice just isn't remembered
    }
  }

  // Saved choice, else the phone's language (French → fr), else English
  function pickStartLanguage() {
    const saved = readSavedLanguage();
    if (LANGUAGES.includes(saved)) return saved;
    const phone = typeof navigator !== "undefined" && navigator.language ? navigator.language : "";
    return phone.toLowerCase().startsWith("fr") ? "fr" : "en";
  }

  // ===== LOADING THE JSON FILES =====
  async function loadDictionary(code) {
    if (dictionaries[code]) return;
    try {
      const res = await fetch("lang/" + code + ".json");
      dictionaries[code] = res.ok ? await res.json() : {};
    } catch (error) {
      dictionaries[code] = {}; // offline and not cached: English fallback / empty
    }
  }

  // ===== TRANSLATE =====
  // params fill {name} placeholders: t("toast.added", { name: "Lunch" })
  function t(key, params) {
    let text = (dictionaries[current] || {})[key];
    if (typeof text !== "string" || text === "") text = (dictionaries.en || {})[key];
    if (typeof text !== "string") return "";
    if (params) {
      text = text.replace(/\{(\w+)\}/g, (match, name) => (params[name] === undefined ? "" : String(params[name])));
    }
    return text;
  }

  // ===== PLURALS =====
  // A count-dependent text has two keys: "<base>.one" and "<base>.other". The language's rule (Intl.PluralRules)
  // picks one: en "1 day" / "2 days"; fr counts 0 and 1 as singular ("0 jour", "1 jour"). Kreol uses fr-MU rules
  // (its .one and .other texts are usually the same). {count} is filled in automatically.
  function pluralCategory(count) {
    try {
      return new Intl.PluralRules(LOCALES[current] || "en-MU").select(Number(count) || 0) === "one" ? "one" : "other";
    } catch (error) {
      return Number(count) === 1 ? "one" : "other"; // very old browsers without Intl.PluralRules
    }
  }
  function tPlural(baseKey, count, params) {
    return t(baseKey + "." + pluralCategory(count), Object.assign({ count: count }, params));
  }

  function hasKey(key) {
    return typeof (dictionaries.en || {})[key] === "string";
  }

  // Category / income type value → text in the current language (unknown values are shown as they are)
  function tCategory(value) {
    return CATEGORY_KEYS[value] ? t(CATEGORY_KEYS[value]) : value;
  }
  function tIncomeType(value) {
    return INCOME_TYPE_KEYS[value] ? t(INCOME_TYPE_KEYS[value]) : value;
  }

  // Sets an element's text AND remembers the key, so a language switch re-translates it by itself
  function setText(element, key, params) {
    element.dataset.i18n = key;
    if (params) element.dataset.i18nParams = JSON.stringify(params);
    else delete element.dataset.i18nParams;
    element.textContent = t(key, params);
  }

  // ===== DATES =====
  function getLocale() {
    return LOCALES[current];
  }

  function formatDate(date, options) {
    return new Intl.DateTimeFormat(getLocale(), options).format(date);
  }

  // ===== MONEY (the ONE shared formatter: every amount on screen goes through here) =====
  // Groups of 3 digits. en: "Rs 100,000" / "Rs 1,234.50"   fr + mfe: "Rs 100 000" / "Rs 1 234,50"
  // options.whole = round to whole rupees. Not a number (NaN, Infinity, null) → "Rs 0", never "Rs NaN".
  function formatMoney(amount, options, language) {
    let n = Number(amount);
    if (!isFinite(n)) n = 0;
    if (options && options.whole) n = Math.round(n);
    const english = (language || current) === "en";
    const cents = Math.round(Math.abs(n) * 100); // whole number of cents: no floating-point leftovers
    const digits = String(Math.floor(cents / 100));
    const groups = [];
    for (let end = digits.length; end > 0; end -= 3) groups.unshift(digits.slice(Math.max(end - 3, 0), end)); // 3 digits each
    const grouped = groups.join(english ? "," : "\u00a0"); // fr / mfe: no-break space, so a number never splits
    const paise = cents % 100 ? (english ? "." : ",") + String(cents % 100).padStart(2, "0") : "";
    return (n < 0 && cents ? "-" : "") + "Rs " + grouped + paise;
  }

  // ===== APPLY TO THE PAGE =====
  function applyTranslations(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((element) => {
      const params = element.dataset.i18nParams ? JSON.parse(element.dataset.i18nParams) : undefined;
      element.textContent = t(element.dataset.i18n, params);
    });
    scope.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    scope.querySelectorAll("[data-i18n-aria]").forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAria));
    });
    document.documentElement.lang = current; // "mfe" is the ISO code for Kreol Morisien
    document.querySelectorAll("[data-lang-switch]").forEach((select) => { select.value = current; });
  }

  // Fills every <select data-lang-switch> with EN / FR / KM
  function setUpSwitchers() {
    document.querySelectorAll("[data-lang-switch]").forEach((select) => {
      select.replaceChildren();
      LANGUAGES.forEach((code) => {
        const option = document.createElement("option");
        option.value = code;
        option.textContent = SHORT_NAMES[code];
        select.append(option);
      });
      select.value = current;
      select.addEventListener("change", () => setLanguage(select.value));
    });
  }

  // ===== SWITCH LANGUAGE =====
  async function setLanguage(code) {
    if (!LANGUAGES.includes(code)) code = "en";
    await loadDictionary(code);
    current = code;
    saveLanguage(code);
    if (typeof document === "undefined") return; // Node tests
    applyTranslations();
    window.dispatchEvent(new CustomEvent("i18n:change", { detail: { language: code } }));
  }

  // ===== START (browser only) =====
  // Hide the page until the texts are ready, so nobody sees English flash before French
  let ready = Promise.resolve();
  if (typeof document !== "undefined") {
    document.documentElement.classList.add("i18n-loading");
    ready = (async () => {
      current = pickStartLanguage();
      await Promise.all([loadDictionary("en"), loadDictionary(current)]); // English is always the fallback
      setUpSwitchers();
      applyTranslations();
      document.documentElement.classList.remove("i18n-loading");
    })();
  }

  // ===== FOR TESTS: load dictionaries without fetch =====
  function useDictionaries(all, code) {
    Object.assign(dictionaries, all);
    current = code;
  }

  const I18n = {
    LANGUAGES, CATEGORY_KEYS, INCOME_TYPE_KEYS, ready,
    t, tPlural, hasKey, tCategory, tIncomeType, setText, setLanguage, getLocale, formatDate, formatMoney,
    applyTranslations, useDictionaries,
    getLanguage: () => current,
  };

  if (typeof window !== "undefined") {
    window.I18n = I18n; // browser: short global names for the other scripts
    window.t = t;
    window.tPlural = tPlural;
    window.setText = setText;
    window.setLanguage = setLanguage;
    window.tCategory = tCategory;
    window.tIncomeType = tIncomeType;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = I18n; // Node tests
})();
