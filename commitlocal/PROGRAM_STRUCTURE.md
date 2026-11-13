# PROGRAM_STRUCTURE.md

> This file explains how the app is built. **Read it before coding. Update it after any change** to files, features or logic.

---

## 1. What the app is

A money app for young people aged **16–25**. It helps them:

- **Track money in and out**: regular income, one-off income, everyday spending, fixed monthly bills.
- **Budget** each spending category and follow the **50 / 30 / 20 rule** (needs / wants / savings).
- **Log expenses fast**: by typing, by voice ("I spent 245 on lunch"), or with one tap on a "Quick add" chip.
- **Save toward targets**: a monthly saving target, a safety net, and goals with deadlines and priorities.

It is a **Progressive Web App (PWA)**. It opens in any phone browser (Chrome, Safari, Samsung Internet), can be added to the home screen, and still opens when offline.

The app has **4 tabs** in a bottom tab bar: **Money**, **Targets**, **Loans**, **Arcade**.

**Status:** ✅ Login + registration (with OTP countdown / Resend) is built. ✅ Full Money tab (month switcher, Left to spend card, Money in / Money out, budgets, fixed bills, recent) and Targets tab (bank balance, monthly saving, safety net, goals) restored from the earlier version, plus the Loans tab. ✅ Arcade has the **Budget Challenge** game. 📝 Voice is **planned**. All amounts are in rupees, shown as **Rs**. ✅ The whole app is in **English, French and Kreol Morisien** (picker EN / FR / KM on the login page and next to Log out).

---

## 2. Folder and file structure

✅ = built · 🆕 = planned in this task · (later) = planned, not part of this task

```
commitlocal/
├── PROGRAM_STRUCTURE.md        ← this file: how the app is built
├── README.md                   ← short "how to install and run"
├── .gitignore                  ← keeps .env, the database and junk files out of git
│
├── frontend/                   ← everything the browser sees (HTML, CSS, plain JS)
│   ├── index.html              ← ✅ 4 tab pages (Money, Targets, Loans, Arcade), floating tab bar, pop-up "sheets" (expense, income, budget, bank, target, goal, add money, lists)
│   ├── login.html              ← ✅ Login / Register tabs, "enter your code" box, "account locked" box
│   ├── login.js                ← ✅ tabs, live password strength meter, Show/Hide password buttons, code countdown + Resend OTP, calls /api/auth/...
│   ├── style.css               ← ✅ dark navy glass theme (CSS variables at the top), cards, tab bar, bars (mobile-first, 360 / 390 / 430 px)
│   ├── api.js                  ← ✅ callApi() + one small function per endpoint (getSummary, addExpense, getGoals…); throws a friendly Error; 401 → login page
│   ├── app.js                  ← ✅ login check, log out, tab switching (PAGES list), toasts, money/date formatting, open/close sheets, service worker
│   │                              (replaced home.js, which is deleted)
│   ├── money-tab.js            ← ✅ month switcher, summary card + 50·30·20 bar, Money in/out views, quick-add chips, category budgets, fixed bills, recent, Add expense/income/budget sheets, category pop-up (tap a category row)
│   ├── budget-calc.js          ← ✅ spent-vs-budget maths (left / over / bar %, colour level); window.BudgetCalc + Node module.exports; loaded before money-tab.js
│   ├── loan-calc.js            ← ✅ loan maths only (amortisation, extra payments, affordability, repaymentFor = EMI for an amount); window.LoanCalc + Node module.exports
│   ├── game-calc.js            ← ✅ Budget Challenge live totals / split % / bar widths (pure, Node-tested; display only)
│   ├── arcade-tab.js           ← ✅ Arcade tab: Budget Challenge game (levels, fields, event, result, previous results)
│   ├── loans-tab.js            ← ✅ Loans tab: forms, results, Chart.js graphs (CDN chart.js@4.4.1, hidden offline); section 2 calls /api/loans/predict
│   ├── targets-tab.js          ← ✅ draws the Targets tab; New goal form; Add money; edit bank balance / monthly target
│   ├── voice.js                ← 🆕 microphone → text (Web Speech API, or record audio for /api/speech-to-text)
│   ├── manifest.json           ← 🆕 app name, icons, colours, start page, "standalone" (makes it installable)
│   ├── service-worker.js       ← 🆕 caches the app files so the app opens with no internet
│   ├── icons/                  ← 🆕 icon-192.png, icon-512.png, apple-touch-icon.png (180×180)
│   ├── i18n.js                 ← ✅ languages: t(key), setText(), setLanguage(code), EN / FR / KM picker; loaded FIRST in index.html + login.html
│   ├── lang/en.json, fr.json, mfe.json ← ✅ one dictionary per language (English, French, Kreol Morisien), same keys in all three
│   └── offline.js              ← (later) queue expenses added offline
│
└── backend/                    ← Python + FastAPI: all logic, data and API keys
    ├── main.py                 ← ✅→🆕 starts FastAPI, connects all the routes, serves the frontend folder
    ├── database.py             ← ✅ SQLAlchemy connection from DATABASE_URL (SQLite or PostgreSQL), open_db(), runs Alembic, user-filtered query helpers
    ├── models.py               ← ✅ incoming forms (Pydantic) + the database tables (SQLAlchemy ORM, see section 6)
    ├── migrate_old_db.py       ← ✅ ONE-TIME: copies users + data from the old finance.db into the new tables
    ├── alembic.ini, migrations/ ← ✅ Alembic database migrations (migrations/versions/0001_new_secure_tables.py, 0002_profile_language.py, 0003_goal_category.py, 0004_game_attempts.py)
    ├── errors.py               ← ✅ AppError(status, CODE, message, params) + handlers: every error reply = {detail, code, params}
    ├── security.py             ← ✅ password rules, bcrypt (14 rounds), 6-digit codes, session tokens
    ├── email_sender.py         ← ✅ emails the 6-digit code through Gmail
    ├── categories.py           ← ✅ CATEGORIES (+ default need/want) · 🆕 the other fixed lists: categories (+ default Need/Want), income types, frequencies
    ├── game/                   ← ✅ Budget Challenge logic (no UI, no routes): scenarios.py = config (levels, categories, min_amount, locked, events, points — edit here),
    │                             events.py (pick + effect), budget_engine.py (checks, totals in cents, over-income block), scoring.py (score + feedback)
    ├── money.py                ← 🆕 ALL the maths, as plain functions with no database (easy to test) — see section 3
    ├── expense_parser.py       ← 🆕 "I spent 245 on lunch" → {amount: 245, category: "Food & drinks", note: "lunch"}
    ├── routes/
    │   ├── auth.py             ← ✅ /api/auth (+ `require_user` helper: 401 if not logged in) + /resend-code
    │   ├── summary.py          ← 🆕 /api/summary: everything the Money tab's dark card + category rows need
    │   ├── income.py           ← 🆕 /api/income: list, add, edit, delete
    │   ├── expenses.py         ← ✅ /api/expenses: list, add · 🆕 edit, delete; quick-add chips
    │   ├── budgets.py          ← ✅ /api/budgets: per-category monthly limits (list / set / remove)
    │   ├── savings.py          ← 🆕 /api/savings: bank balance, monthly target, safety net (+ add money to it)
    │   ├── goals.py            ← 🆕 /api/goals: list (with status), add, edit, delete, add money, GET /{id}/inflation-projection
    │   ├── inflation.py        ← ✅ GET /api/inflation/projection (live preview for the goal form)
    │   ├── loans.py            ← ✅ /api/loans/predict: real-data risk model (loaded once at start) searched in Rs 5,000 steps + 40% rule; final = lower of the two
    │   └── voice.py            ← 🆕 /api/voice/parse-expense and /api/speech-to-text (calls OpenAI)
    ├── AI_model/loan_risk_model.pkl + loan_risk_model_card.json ← ✅ HistGradientBoostingClassifier on real Lending Club outcomes + its facts (rows, dates, AUC, base default rate, bands); git-ignored
    ├── AI_model/loan_amount_model.pkl ← ❌ old synthetic RandomForest, NOT used (kept on disk)
    ├── train_loan_risk_model.py ← trains the risk model: `--input loan.csv --out-dir AI_model` (chunked pandas read, filters + logs removed rows)
    ├── DATA/lending_club/loan.csv ← Kaggle "All Lending Club loan data" (1.2 GB, git-ignored)
    ├── train_loan_model.py     ← ❌ old synthetic training script, NOT used
    ├── DATA/synthetic_loan_data.csv ← ❌ old synthetic data, NOT used
    ├── requirements.txt        ← ✅→🆕 adds: pytest, httpx (tests + calling OpenAI), python-multipart (audio upload), sqlalchemy, alembic, psycopg[binary] (PostgreSQL), scikit-learn==1.9.1 + pandas + joblib (loan model)
    ├── .env.example            ← names of the keys, with no real values (safe to commit)
    ├── .env                    ← YOUR real keys (never committed, never sent to the browser)
    ├── app.db                  ← the SQLite database file in development (created automatically, not committed)
    └── finance.db              ← the OLD database (only read by migrate_old_db.py)

tests/backend/test_loans.py ← ✅ /api/loans/predict: rule, AI search with fake models, fallbacks, real-model sanity (skipped if not trained), training script on tests/fixtures/lending_club_sample.csv (FAKE TEST DATA)
tests/backend/test_error_codes.py ← ✅ every error reply has a "code" (422 field codes, AppError codes + params), "detail" kept
tests/backend/test_game.py ← ✅ Budget Challenge: exact income, unallocated, over income rejected, no savings, needs>50%, wants>30%, essentials, cost/discount/bonus events, L3 reaches 100, locked values, XP once + replay, +20 once, per user, 401, money tables untouched, decimals
tests/frontend/game-calc.test.js ← ✅ game-calc.js (cents, never NaN, UTC→local dates) + every game/scenarios.py id / criterion / tip has a text
tests/frontend/loan-calc.test.js ← ✅ Node built-in tests for loan-calc.js (run: node --test tests/frontend)
tests/frontend/i18n.test.js     ← ✅ same keys + no empty values in en/fr/mfe, t() fallback, every data-i18n / t("…") / backend error code has a translation
tests/frontend/budget-calc.test.js ← ✅ no budget, under / at / over, colour thresholds 79/80/100/101%
tests/backend/test_inflation.py ← ✅ CPI builder (temp files), 12-month rate, projection + edge cases, endpoints (uses tests/fixtures/cpi_sample.csv = FAKE data)
tests/backend/                  ← pytest + FastAPI TestClient (temporary database, fake email — never sends real emails)
    ├── conftest.py             ← ✅ fixtures: fresh temp DB per test (runs the migrations), fake email sender, logged-in clients
    ├── test_otp.py             ← ✅ valid / expired / wrong code, hashes only, lowercase email, locked-account unlock
    ├── test_money.py           ← ✅ expenses (incl. bad amounts), cents storage, UUIDs, budgets, income, savings, goals
    ├── test_budgets_expenses.py ← ✅ budget set/update + /api/budget alias, bad input, add/edit/delete, month+category filter, other users
    ├── test_security_db.py     ← ✅ user A can't read/edit/delete user B's data, ON DELETE CASCADE, CHECK (no negative amounts)
    ├── test_auth.py            ← ✅ register (valid / duplicate / missing / weak), login (right / wrong / unknown), /me, Gmail not set up → 503 (SMTP faked)
    ├── test_income_summary.py  ← ✅ regular vs one-off income per month, fixed bills, budget none/under/at/over, summary maths (In/Out/Saved/Left, 50·30·20 %)
    └── test_route_safety.py    ← ✅ reads EVERY /api route from main.app: 401 when logged out; no 500 on empty / negative / 1e20 / Infinity / NaN / text input
tests/frontend/smoke.test.js    ← ✅ static checks: script order, every called function defined, every JS id exists in the HTML, manifest + icons, SW caches scripts, no API keys, .gitignore / .env.example

**Run all tests** (from the project folder):
`backend\venv\Scripts\python -m pytest tests/backend -q` and `node --test tests/frontend`
```

**Rule of thumb:** if logic *can* run in Python, it goes in `backend/`. JavaScript only shows screens, sends forms, uses the microphone, and caches files for offline.

---

## 3. How the logic works

### Login and registration ✅
1. **Register** → name, email, password twice → the strength meter turns red→green and ticks each rule → Python checks the rules again → the email is saved in lowercase (so `Asha@X.com` = `asha@x.com`) → the password is saved as a **bcrypt hash (14 rounds)**.
2. **Log in, step 1** → email + password → if correct, Python emails a **6-digit code** through Gmail (it expires in **5 minutes**).
3. **Log in, step 2** → the user types the code → if correct, Python creates a session and puts it in an **HttpOnly cookie** (JavaScript can't read it) → the user is logged in for 7 days.
4. **3 wrong passwords** → the account is **locked**, and even the right password won't work → the user taps **"Send me a login code"** → enters the emailed code → logged in **and unlocked**.
5. **Safety limits:** a code dies after 5 wrong guesses; a new code replaces the old one; a new unlock code ("Send me a login code") can only be sent once every 60 seconds.
6. **After registering** → the app switches to the Login tab, fills in the email, shows "Account created, please log in" and **hides the Register tab**. The link "Don't have an account? Register" under the login form brings it back.
7. **Code screen countdown** → login / send-login-code / resend-code reply with `expires_in` (300) and `resend_wait` (30). `login.js` shows "Code expires in 4:32", ticking every second. At 0:00 → "Your code has expired. Please request a new one." and Verify is disabled.
8. **Resend OTP** (`POST /api/auth/resend-code`) → clears the input, emails a new code (old one stops working), restarts the 5-minute timer. **30-second cooldown**: the button shows "Resend OTP (25s)" and is disabled; the backend also refuses (429) if the last code is under 30 s old. Only works if the user got a code in the last 30 minutes (400 otherwise).
9. **Expired code typed in** → `/verify-code` returns **410** → the app shows the same expired message + Resend button.


### Pop-ups (`app.js`) ✅
- A pop-up closes **only** from its X / Cancel buttons (`data-close`), after a successful save, or a tap on the **dark overlay itself** (`event.target === overlay`, and the press must also have *started* on the overlay).
- There are **no** blur / focusout / resize handlers, so the phone keyboard opening (which resizes the screen) can't close it. The box has `max-height: 90dvh; overflow-y: auto`, so it scrolls instead.
- Every button that isn't "Save" has `type="button"`, so it never submits a form.

### Money tab ✅ (restored full version — see Section 4, Tab 1)
- Uses GET `/api/summary`, `/api/expenses`, `/api/expenses/quick`, `/api/income`; POST/PUT/DELETE expenses + income; PUT `/api/budgets` (`monthly_limit: null` removes). Targets uses `/api/savings`, `/api/savings/safety-net/add-money`, `/api/goals` (+ `/{id}/add-money`). All checked against the backend routes.
- *Old notes from the simple version (replaced):*
- Tap the **Expenses** card → pop-up with **Add expense** (amount, category, description, date = today) or **Set budget** (category + monthly limit → PUT `/api/budgets`).
- Budget card: **overall budget = sum of all category budgets** (GET `/api/budgets`); **spent = everyday + fixed bills** of this month (GET `/api/expenses` → `everyday` + `fixed`).
- After a save the pop-up closes and the list, total and budget bar reload at once.
- Budget card: "Spent Rs X of Rs Y" + bar: **green** < 75%, **orange** 75–100%, **red** over budget + "⚠ Over budget by Rs X". No budget yet → "no budget set yet".
- Amounts are checked in `money-tab.js` (empty / 0 / negative / > 10,000,000 → message) and again by Pydantic on the backend (422).

### Tab 4: Loans ✅ (section 1 client-side; section 2 uses POST /api/loans/predict)
- **My current loan:** amount left, rate (% a year), monthly repayment, optional extra per month + start date → months/years to repay, payoff date (from the start date, or today if empty/past), total interest, total paid. Month-by-month amortisation (monthly compounding). Payment ≤ first month's interest → warning; > 100 years → warning. Graphs: balance line (+ "with extra" line), donut loan vs interest.
- **Can I afford a loan? (How much can I borrow?):** income, expenses (pre-filled from this month's /api/summary), existing repayments (pre-filled from section 1), rate, term (1–30 yrs), optional "Missed a loan or bill payment in the last 12 months?" (No/Yes) → POST `/api/loans/predict`. Expenses are not used by the model or the rule (LC's dti excludes living costs).
  - **Risk model** (`train_loan_risk_model.py`, real data only): Lending Club loans issued 2007-06…2015-12 with a final outcome — Fully Paid = 0, Charged Off / Default = 1 ("Does not meet the credit policy. Status:X" kept with outcome X); Current/Late/Grace dropped. Features (ratios only, no FICO/grade/zip/demographics), in order: `payment_to_income` (installment ÷ monthly income), `dti` (LC dti ÷ 100 = existing debt excl. this loan), `loan_to_income` (loan ÷ annual income), `int_rate` (%), `term_months` (36/60), `missed_payment` (delinq_2yrs > 0). Monotonic constraints: more burden never lowers risk. 80/20 stratified split, random_state 42. Card: 825,536 rows, test ROC-AUC 0.705, base default rate 18.5%.
  - **Search** (`routes/loans.py`): amounts Rs 0, 5,000, … up to min(Rs 1 crore, 5 × yearly income); installment by amortisation at the user's rate/term; term clipped to 36–60 months for the model. AI estimate = largest amount (from 0 upward, stopping at the first failure) whose risk ≤ base default rate (from the card) AND whose installment ≤ 30% of income (`MAX_PAYMENT_TO_INCOME`; real data has almost no loans above that). Final `predicted_max_loan` = min(AI, 40% rule), `limited_by` "ai"/"rule". Risk shown for the final amount (Rs 5,000 if 0): low < 0.8 × base, medium ≤ 1.2 × base, high above.
  - **40% rule:** payment = 40% income − existing repayments (min 0) → present value at the rate/term. Displayed DTI = existing repayments ÷ income → verdict <30% "Good to borrow", 30–40% "Borrow carefully", >40% "Not recommended right now".
  - **Fallback:** model or card missing/broken → logged error, `source: "formula"`, answer = rule amount, AI fields null.
  - **UI:** final answer, which limit applied, "AI estimate: about Rs X (risk model trained on N real loan outcomes)", risk Low/Medium/High, DTI bar, verdict, rule line, EMI for the final amount, graph rule-max per term vs flat AI line, "How is this calculated?" (N and years from the card via the API), "Estimate only – not financial advice. Your bank makes the final decision."
- Money shown as "Rs 12,345" (whole rupees); empty / negative / text inputs → friendly message. Tests: `node --test tests/frontend`.

### Languages (`i18n.js`, `lang/*.json`, `backend/errors.py`) ✅
- **Start language:** saved choice (`localStorage "language"`, in try/catch) → else phone language (`fr…` → French) → else English. `<html lang>` follows (`en` / `fr` / `mfe`).
- **Loading:** `i18n.js` fetches `lang/en.json` (always, it's the fallback) + the chosen language; `I18n.ready` is a promise. `app.js` (`startApp`) and `login.js` (`startLoginPage`) `await I18n.ready` before drawing anything; the page is hidden (`.i18n-loading`) until then. The service worker caches the 3 JSON files (offline works).
- **`t("key", {name: …})`** → text in the current language, English if missing, `""` if unknown (never the raw key / "undefined"). `{name}` placeholders are filled from the object.
- **HTML:** `data-i18n="key"` (text), `data-i18n-placeholder`, `data-i18n-aria` (aria-label), `data-i18n-params='{"n":1}'`. Text next to an input inside a `<label>` is wrapped in `<span data-i18n>`.
- **JS:** `t("key")` for built text; `setText(element, key, params)` for elements that should re-translate by themselves (titles, hints).
- **Switching:** `setLanguage(code)` → re-applies every `data-i18n`, then fires `i18n:change`; `app.js` redraws the open tab (`redrawMoneyTab` incl. the open category pop-up, `loadTargetsTab`, `redrawLoans` incl. graph labels); `login.js` redraws the meter / code timer.
- **Kept English on purpose:** values sent to the API (categories, income types, `On track` status, bar labels "Safety net"/"Free") — only their DISPLAY is translated (`tCategory`, `tIncomeType`, `STATUS_KEYS`, `PRIORITY_KEYS`). Money is always "Rs 12,345". Dates use `Intl.DateTimeFormat` (`en-MU`, `fr-MU`; Kreol uses French month names).
- **Backend error codes:** routes raise `AppError(404, "GOAL_NOT_FOUND", "Goal not found.")`; Pydantic 422 errors get a code from the field name (`FIELD_CODES` in `errors.py`, e.g. amount → `INVALID_AMOUNT`). Reply: `{"detail": <English message or the old Pydantic list>, "code": "...", "params": {...}}`. `readErrorMessage` (api.js) / `readMessage` (login.js) show `t("error.<CODE>")` (or `auth.<CODE>` for good news) and fall back to `detail`. The backend never translates.
- **Add a new string:** add the key to `en.json`, `fr.json` AND `mfe.json` (the tests fail if one is missing or empty), then use `data-i18n="key"` or `t("key")`.
- **Add a new language:** copy `en.json` to `lang/<code>.json` and translate it; add the code to `LANGUAGES`, `SHORT_NAMES`, `LOCALES` in `i18n.js`; add the file to `APP_FILES` in `service-worker.js` (bump `CACHE_NAME`); add it to the list in `tests/frontend/i18n.test.js`.

### Every money route
- Reads the session cookie → finds the user → **401 if not logged in** (the app then goes to `login.html`).
- Every row has a `user_id`. Every ORM query filters by the logged-in user's id, so you can only see or change **your own** rows (someone else's id → 404, a non-UUID id → 422).
- Amounts must be **more than 0 and at most 10,000,000**, rounded to 2 decimals. Dates are `YYYY-MM-DD`, months `YYYY-MM`.

### Fixed lists (`categories.py`) 🆕
| Category | Default kind |
|---|---|
| Groceries, Transport, Bills, Utilities, Other | Need |
| Food & drinks, Shopping, Subscriptions, Fun & outings | Want |

- Income types: Salary, Allowance, Side hustle, Scholarship, Other.
- Income frequency: `monthly`, `weekly`, `one-off`.
- Goal priority: `1` = High, `2` = Medium, `3` = Low.

### The maths (`money.py`, all on the backend) 🆕
"This month" means the month picked at the top of the Money tab (default: the current month).

1. **Monthly income** = monthly incomes + weekly incomes × 52 ÷ 12 + one-offs dated this month.
   Monthly/weekly incomes count in every month **from their start date's month onwards**.
2. **Repeating items are never copied.** A regular income or fixed bill is one row; it is simply counted in every month from its date onwards.
3. **Spent this month** = fixed bills (from their start month onwards) + everyday expenses dated this month.
4. **Saved this month** = deposits dated this month (goals + safety net).
5. **Left to spend** = monthly income − spent − saved.
6. **Needs % / Wants % / Savings %** = needs total, wants total, saved ÷ monthly income × 100 (0 if there is no income). Shown next to "aim 50 · 30 · 20".
7. **Category rows** (Everyday spending card) = everyday expenses this month per category, with that category's budget. Over budget → `over_by` = spent − budget. *Fixed bills are not in these rows — they have their own card.*
8. **Monthly saving target** = `savings.monthly_target` if the user set one, otherwise **20% of regular income** (monthly + weekly × 52 ÷ 12, no one-offs).
9. **Safety net target** = 3 × the total of fixed monthly bills. % reached = safety_net_saved ÷ target × 100 (max 100).
10. **Goal "needs per month"** = (target − saved) ÷ months left. Months left = months from this month to the deadline's month, **at least 1**.
11. **Goal status:** go through goals by priority (High first; same priority → earlier deadline first). Give each goal money from the monthly saving target until it runs out. A goal that gets at least what it needs = **On track**, otherwise **Needs more**. A finished goal (saved = target) = **Done**.
12. **Too-many-goals warning:** if all goals together need more per month than the saving target → "Your goals need Rs X a month, but you save Rs Y. Push a date back or focus on one goal first."
13. **Adding money to a goal** → save a deposit, add it to `goal.saved_amount` and to `savings.bank_balance`. The amount must be positive and can't push saved above target (it is capped at what's still needed). Adding to the **safety net** works the same, using `safety_net_saved` (deposit with empty goal_id).
14. **Bank bar** (Targets dark card) = bank_balance split into: safety net, one segment per goal (its saved amount), and the rest ("free").
15. **Quick add chips** = everyday expenses from the last 30 days, grouped by (note, amount), the 4 most frequent (ties → most recent). One tap → `POST /api/expenses/quick` saves the same expense again with today's date and `source = "quick"`.

### Inflation estimate for goals (Statistics Mauritius CPI) ✅
- Data: `data/cpi_mauritius.csv` (month, category, index_value, base_year, source_file; base 2023 = 100), built from the transcribed official releases in `data/cpi_raw/` (never edit) by `python scripts/build_cpi_csv.py`. 2025-09 → 2026-10, 14 categories.
- `backend/services/inflation.py` loads it once at startup (`load_cpi()` in main.py; path from the project root). Missing file → `{"available": false, "reason": "DATA_UNAVAILABLE"}`.
- Rate r = index[latest] / index[latest − 12 months] − 1 (3-year average only if 37+ months; not the case now). Months = whole months to the deadline. projected_cost = target × (1 + r)^(months/12), rounded to the rupee; monthly saving original/adjusted = (target or projected − saved) ÷ months.
- Goal category → CPI category: `GOAL_CPI_CATEGORIES` in `categories.py` (edit there). No/unknown category or < 13 months → "All Items" (+ FALLBACK_ALL_ITEMS warning).
- Edge cases: deadline passed / < 1 month → `available: false` (DEADLINE_PASSED / DEADLINE_TOO_SOON); > 5 years → LONG_HORIZON warning; falling prices handled normally; fully funded → FUNDED_BUT_SHORT if the projection is above what's saved.
- Frontend (`targets-tab.js`): each goal card fetches its estimate; the goal form has a "What is it for?" select and a live preview (400 ms after typing). Texts: `inflation.*`, `goalCat.*`, `cpi.*` keys. Always labelled "Estimate only" with source and data month.

### Voice → expense 🆕
1. User taps the mic (on the Everyday spending card, or "Say it" on Add expense).
2. `voice.js` uses the browser's **Web Speech API** to get the words. If the browser doesn't have it (often iPhone / Samsung Internet), it **records a short clip** (`MediaRecorder`) and sends it to `POST /api/speech-to-text` → Python sends it to OpenAI → text comes back.
3. The text goes to `POST /api/voice/parse-expense` → `expense_parser.py`:
   - the first number = amount ("245", "1,200", "Rs 38"),
   - keywords in a Python dictionary → category (lunch/kfc/burger/snack/coffee → Food & drinks; bus/taxi/fuel → Transport; supermarket/groceries → Groceries; netflix/spotify → Subscriptions; …; no match → Other),
   - filler words removed ("I", "spent", "on", "rupees", …), the rest = note.
4. The **Add expense form is filled in** (with source = voice). The user checks it and taps **Save**. Nothing is saved without that tap.
5. No OpenAI key, or no microphone allowed → a friendly message: "Voice isn't available here — type it instead."

---

## 4. Screens 🆕

**Design (current):** dark blue banking "glass" theme. CSS variables at the top of `style.css`: navy gradient background `#070d1f`→`#0d1a3a` with blue/cyan glows, frosted translucent cards (`backdrop-filter: blur`), glowing blue gradient buttons, cyan→blue progress bars, floating frosted 4-tab bar, dark bottom sheets. Green `#3ddc84` = money in, orange `#ff9a4a` = money out. Chart.js in blue/cyan/green/orange with light text. Manifest + meta theme `#070d1f`; SW cache `my-money-v9`. Inputs 16px, tap targets ≥ 44px.

*Previous design (replaced):* light, clean theme. CSS variables at the top of `style.css`: grey background `#f3f5f8`, white 18px-rounded cards with thin `#e6e9ef` border, dark `#15171d` budget card, solid royal-indigo `#2f3fbf` buttons/links, grey segmented tabs with white active pill, green in `#1e8e4f` / orange out `#e0650b`, text `#1b1d24`, muted `#6b7280`, light-indigo tip boxes. White floating tab bar, light bottom-sheet pop-ups, Chart.js in indigo/green/orange. Manifest + meta theme `#F3F5F8`; SW cache `my-money-v7`.

Colours: background `#F6F7F9`, white cards (20px corners), dark summary card `#14161A`, active tab blue `#2F4BC0`.
**Income = green `#237032` with "+"**, **expenses = orange `#A34A00` with "−"** — everywhere.
Fonts: **Space Grotesk** (headings), **Inter** (text), from Google Fonts. Every button is at least **44px** tall.
A small **Log out** button sits at the top right of each tab.

### Tab 1: Money
- Title "Money" + month picker.
- **Dark card:** big "Left to spend this month"; small In (+green) · Out (−orange) · Saved; Needs/Wants/Savings bar + "aim 50 · 30 · 20".
- Switch **[Money in] [Money out]** — Money out shows first.
- **Money out:**
  1. *Everyday spending* — mic button, "+ Add expense", Quick add chips ("Bus Rs 38"), one row per category: spent / budget + bar. Over → orange-red bar + "⚠ Over budget by Rs X". No budget → spent + "Set budget" link. Bar colour (budget-calc.js): blue < 80%, amber 80–100%, red > 100%. **Tap a row** (or "Set budget"/"Edit") → category pop-up: month, "Rs X of Rs Y", bar, "Rs Z left"/"Rs Z over budget", Budget box + Save (empty = remove), Add expense (amount, note, date = today, "Repeats every month"), list of this month's expenses in that category (fixed bills after, marked "Every month"); tap one → edit in the same form or Delete (confirm). After every save the whole tab reloads (summary card, rows, recent) and the pop-up redraws.
  2. *Fixed monthly* — number of bills, total, bill names as small tags, "View or edit bills" → full list (edit / delete).
  3. *Recent* — last 3 expenses of the month + "See all" → full list of the month (edit / delete).
- **Money in:**
  1. *Regular income* — monthly / weekly incomes, each with an "Auto" tag, "+ Add income".
  2. *One-off this month* — gifts, freelance, prizes.
  3. Tip: "You only add regular income once. After that it's added every month."
- **Add expense** screen: big Rs amount, "Say it" button, category grid, Need/Want toggle (pre-picked from the category, can be changed), note, date (today), "Repeats every month" (= fixed bill), Save.
- **Add income** screen: name, type, amount, how often (Monthly / Weekly / One-off), date.

### Tab 2: Targets
1. **Dark card:** "Saved in your bank" (tap to update) + bank bar (safety net + one colour per goal + free).
2. **Monthly saving:** target per month (editable) + "Rs 2,500 of Rs 3,700 put away".
3. **Safety net:** target = 3 × fixed bills, % reached, "+ Add money".
4. **Goals** + "+ New goal": name, deadline, priority, progress bar, "saved of target", "Needs Rs X a month", tag (On track / Needs more / Done), "+ Add money".
5. **Warning box** when goals need more than the saving target (logic step 12).

### Tab 3: Loans — see "Tab 4: Loans" in Section 3.

### Tab 4: Arcade
**Budget Challenge** card first (Game 1), then Play / Result / Previous results cards, then the old "Coming soon" card + dashed boxes [Game 2]–[Game 4].
- **Config** (`backend/game/scenarios.py`, GET `/api/game/levels`; amounts fictional, said in the UI): L1 "Student Life" Rs 15,000 (Food and groceries, Transport, Phone and internet, Study materials, Entertainment, Personal expenses, Savings; nothing locked) · L2 "First Job" Rs 30,000 (Rent or household contribution, Groceries, Transport, Utilities, Phone and internet, Entertainment, Shopping, Savings, Loan repayment 🔒 Rs 2,500) · L3 "Independent Living" Rs 45,000 (Rent 🔒 Rs 12,000, Groceries, Electricity and water, Transport, Phone and internet, Healthcare, Entertainment, Personal expenses, Savings, Loan repayment 🔒 Rs 3,000). Groups: Needs 50% · Wants 30% · **Savings & debt** 20% (loan repayments are here). Essentials have `min_amount`. 4 events per level: `cost` (raises a category's minimum), `discount` (lowers it), `bonus` (adds income); e.g. bus fare +500/700, grocery discount 300/500/600, charger 400, utilities +600/900, doctor 1,200, bonus 1,000/1,500/2,000. Texts: `game.cat.<id>`, `game.event.<id>`, `game.levelTitle.<n>`, `game.levelStory.<n>`, `game.group.*`, `game.crit.*`, `game.tip.*`.
- **Flow:** pick level (events toggle for every level, default on) → POST `/api/game/attempts` (server makes `attempt_id`, picks the event, keeps it secret) → fill amounts (🔒 fields disabled, "Suggested at least Rs X", live Allocated / Remaining, per-group % + Rs bar; over income → red warning and Submit disabled, server also answers 400 `GAME_OVER_INCOME`; unallocated money is allowed) → submit (`final:false`) → event + its effect shown, hints/income updated → adjust once → `final:true` → result: income, allocated, remaining, group bars vs 50·30·20, breakdown, feedback, XP; Play again / Choose another level / Previous results (dates shown in the phone's local time). Events off → straight to final.
- **Score (server, `game/scoring.py`, cents):** budget balance 30 (within income: ≤10% unallocated = 30, ≤25% = 20, more = 10) · essential coverage 25 (share of essentials ≥ min; a discount lowers the min) · allocation 20 (distance to 50·30·20; if the scenario's need minimums exceed 50%, the Needs target rises and Wants shrinks; Needs above target count half; ≤10 → 20, ≥50 → 0) · savings 15 (Savings category up to 10% of income, nothing extra above; max 5 if an essential is short) · events 10 (within income and the event-raised minimums met; events off → automatic 10; a missed cost event only loses these 10). Feedback codes explain each part (balanced, essential_short, high_needs_ok, large_wants, unassigned, …).
- **XP:** score + 20 the first time a level is completed. Given once per attempt (`UPDATE … WHERE xp_awarded = false`); repeat submits return the saved result with `xp_awarded: 0`. Only `game_attempts` is written — never income/expenses/budgets.

---

## 5. How the parts connect

```
   PHONE (browser / installed PWA)                 OUR SERVER (Python)                 EXTERNAL APIs
 ┌───────────────────────────────┐          ┌──────────────────────────────┐
 │ index.html + style.css        │          │ main.py (FastAPI)            │
 │ app.js ── tabs, pop-ups       │  fetch   │  routes/summary, income,     │
 │ money-tab.js, targets-tab.js  │─────────►│  expenses, budgets, savings, │
 │ api.js ── talks to backend    │  /api/…  │  goals, voice                │
 │ voice.js ── microphone        │◄─────────┼──    ▼                       │
 │ service-worker (offline)      │   JSON   │  money.py, expense_parser.py │
 │                               │          │  database.py ──► SQLite/PG   │
 │ Free browser feature:         │          │                              │
 │  • Web Speech API (mic)       │          │  routes/voice.py ────────────┼──► OpenAI (speech-to-text,
 └───────────────────────────────┘          │  .env (API keys live ONLY here)     only if the browser can't)
                                            └──────────────────────────────┘
```

The browser **never** talks to OpenAI directly, and it never sees a key. It only calls our own `/api/...` addresses.

---

## 6. Data stored for each item

One database, read with **SQLAlchemy** (ORM) from `DATABASE_URL` in `.env`: **SQLite** file `backend/app.db` while developing (the default), **PostgreSQL** (Supabase / Neon) in production — the same code works on both. Tables live in `models.py` (bottom); they are created and changed by **Alembic** migrations in `backend/migrations/versions/` (the app runs `alembic upgrade head` when it starts).

**Rules for every table**
- **ids are UUIDs** (random, e.g. `3f2b…`), never 1, 2, 3. The API sends them as text.
- **Money is whole cents** (`BIGINT`): Rs 150.50 → `15050`. The API still takes and returns **rupees** (converted at the edge with `to_cents()` / `to_rupees()` in `money.py`), so the frontend didn't change.
- **CHECK constraints**: amounts can't be negative; `kind` = need/want; `frequency` = monthly/weekly/one-off; `priority` 1–3; `email` must be lowercase.
- **`user_id` → `users.id` ON DELETE CASCADE**: deleting a user deletes all their rows (SQLite needs `PRAGMA foreign_keys=ON`, switched on in `database.py` for every connection).
- **Indexes** on every `user_id` and every date column (`date`, `deadline`, `start_date`).
- **Only ORM queries** (parameterized), never SQL built from strings. Every money query filters by the logged-in user's id (`get_user_rows`, `find_user_row` in `database.py`) — someone else's id → 404.
- **Never stored:** card numbers, bank account numbers, plain-text passwords or codes (bcrypt / SHA-256 hashes only).

```
                         users  (login data only)
                         id UUID PK · email (unique, lowercase) · password_hash
                         failed_attempts · is_locked · created_at
                                         │  user_id FK, ON DELETE CASCADE
   ┌──────────┬───────────┬──────────┬───┴──────┬──────────┬──────────┬──────────────────┬──────────────┐
   ▼          ▼           ▼          ▼          ▼          ▼          ▼                  ▼              ▼
profiles  otp_codes   sessions    income    expenses   budgets  savings_settings  savings_goals ◄─┐ deposits
(1 per    (many)      (many)      (many)    (many)     (1 per   (1 per user)      (many)          │ (many)
 user)                                                 category)                                  └─ goal_id FK
                                                                                                   CASCADE (empty
                                                                                                   = safety net)
```

| Table | Columns (money = `_cents`) | Notes |
|---|---|---|
| `users` | id, email, password_hash, failed_attempts, is_locked, created_at | locked after 3 wrong passwords |
| `profiles` | id, user_id (unique), full_name, date_of_birth (optional), phone (optional), updated_at | personal details, apart from login data |
| `otp_codes` | id, user_id, code_hash, expires_at, attempts, used, created_at | SHA-256 of the 6-digit code; 5 min; dies after 5 wrong guesses; created_at → 30 s resend wait |
| `sessions` | token_hash (PK), user_id, expires_at | SHA-256 of the cookie value; 7 days |
| `income` | id, user_id, name, source, amount_cents, frequency, date, created_at | `source` = Salary/Allowance/… (API field `type`) |
| `expenses` | id, user_id, amount_cents, category, kind, description, date, is_fixed, source, created_at | `description` = API field `note`; `source` = typed/voice/quick; `is_fixed` = repeats monthly |
| `budgets` | id, user_id, category, amount_cents, period ("monthly"), start_date | one per user per category (API field `monthly_limit`) |
| `savings_settings` | id, user_id (unique), bank_balance_cents, monthly_target_cents (empty = 20% of regular income), safety_net_saved_cents | made the first time it's needed |
| `savings_goals` | id, user_id, name, target_cents, saved_cents, deadline, priority, category (optional, e.g. "Phone"), created_at | API fields `target_amount`, `saved_amount` |
| `game_attempts` | id (= attempt_id), user_id, level, events_on, event, stage (start/event/done), allocation (JSON cents), score 0–100, xp, xp_awarded, created_at, completed_at | Arcade Budget Challenge (migration 0004) |
| `deposits` | id, user_id, goal_id (empty = safety net), amount_cents, date, created_at | deleting a goal deletes its deposits |

`created_at` is used to keep "newest first" order (UUIDs have no order). The old `overall_budget` table is gone (not used by the current routes).

**Calculated, not stored** (worked out in `money.py` each time): monthly income, spent, saved, left to spend, the 3 percentages, category spending, monthly saving target (when empty), safety net target, goal needs-per-month and status, quick-add chips.

### Migrations (Alembic)
From the `backend` folder:
```bash
venv\Scripts\alembic upgrade head                                  # create / update the tables (the app also does this on start)
venv\Scripts\alembic revision --autogenerate -m "what changed"     # after changing a table in models.py: makes a new migration file
venv\Scripts\python migrate_old_db.py                              # ONE TIME: copy users + their data from the old finance.db
```
`migrate_old_db.py` reads the old file read-only, gives everyone new UUIDs, converts rupees → cents, and skips emails that are already there (safe to run twice). Login codes and sessions are not copied (users just log in again).

### Switching to PostgreSQL (Supabase / Neon)
1. Create a project → copy the **connection string** (Supabase: Project Settings → Database → URI; Neon: Dashboard → Connection string).
2. In `backend/.env`: `DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require` (`postgres://…` also works; `database.py` switches it to the `psycopg` driver).
3. `venv\Scripts\alembic upgrade head` (or just start the app), then optionally `venv\Scripts\python migrate_old_db.py`.

### API addresses
All money routes need you to be logged in (401 otherwise).

| Method + address | What it does |
|---|---|
| POST `/api/auth/register` ✅ | create an account |
| POST `/api/auth/login` ✅ | check the password → email a code (423 = locked) |
| POST `/api/auth/send-login-code` ✅ | locked account → email a code |
| POST `/api/auth/resend-code` ✅ | "Resend OTP": new code for the same email (429 within 30 s of the last one) |
| POST `/api/auth/verify-code` ✅ | check the code → log in (+ unlock) → set cookie (410 = code expired) |
| GET `/api/auth/me` ✅ | who is logged in + saved `language` (null if never set) (401 if nobody) |
| PUT `/api/auth/language` ✅ | `{language: en/fr/mfe}` saved on `profiles.language` so it follows the user across devices; `app.js` applies it after `/me` and saves each switch (`saveMyLanguage` in api.js, silent on failure); login page stays localStorage-only |
| POST `/api/auth/logout` ✅ | log out |
| GET `/api/summary?month=YYYY-MM` 🆕 | income, spent, saved, left to spend, %s, category rows (spent / budget / over_by), fixed bills, last 3 expenses |
| GET `/api/income?month=YYYY-MM` 🆕 | regular incomes + one-offs of that month |
| POST `/api/income` 🆕 | add an income |
| PUT / DELETE `/api/income/{id}` 🆕 | edit / delete an income |
| GET `/api/expenses?month=YYYY-MM&category=…` ✅ | `{month, everyday: [...], fixed: [...]}` (no total: the frontend adds it up); optional `category` filter (unknown → 422) |
| POST `/api/expenses` ✅ | add an expense `{amount, category, note, date}` (date empty = today) |
| PUT / DELETE `/api/expenses/{id}` 🆕 | edit / delete an expense |
| GET `/api/expenses/quick` 🆕 | top 4 quick-add chips |
| POST `/api/expenses/quick` 🆕 | log a chip again with today's date |
| GET `/api/budgets?month=YYYY-MM` ✅ | the user's budgets (one per category, same every month; `month` optional). `/api/budget` (GET/PUT) = hidden alias for old cached clients |
| PUT `/api/budgets` ✅ | set one category's limit `{category, monthly_limit}` (empty limit = remove it) |
| GET `/api/savings` 🆕 | bank balance, monthly target (+ this month's progress), safety net target / saved / %, bank bar segments |
| PUT `/api/savings` 🆕 | update bank balance and/or monthly target |
| POST `/api/savings/safety-net/add-money` 🆕 | add money to the safety net |
| GET `/api/goals` 🆕 | goals with needs-per-month + status, total needed, warning text (or none) |
| POST `/api/goals` 🆕 | add a goal |
| PUT / DELETE `/api/goals/{id}` 🆕 | edit / delete a goal |
| POST `/api/goals/{id}/add-money` 🆕 | add money to a goal |
| GET `/api/goals/{id}/inflation-projection` ✅ | inflation estimate for one goal (see "Inflation estimate") |
| GET `/api/inflation/projection?target&current&deadline&category` ✅ | same estimate for the goal form preview (nothing saved) |
| POST `/api/voice/parse-expense` 🆕 | text → suggested `{amount, category, kind, note}` (not saved) |
| POST `/api/loans/predict` ✅ | `{monthly_income, monthly_expenses?, existing_debt_payment?, interest_rate?, years?, missed_payment?}` → `{predicted_max_loan, ai_max_loan, limited_by, predicted_risk, risk_level, base_default_rate, model_info{rows,date_from,date_to,dataset}, max_payment_to_income, formula_max_loan, formula_monthly_payment, debt_to_income_ratio, verdict, source}` |
| GET `/api/game/levels` ✅ | Budget Challenge config (levels, points, XP bonus) |
| POST `/api/game/attempts` ✅ | `{level, events_on}` → `{attempt_id, level, events_on, has_event}` (event chosen + stored, not shown yet) |
| POST `/api/game/attempts/{attempt_id}/submit` ✅ | `{allocation: {category: rupees}, final}` → score, breakdown, percents, tips, event (after 1st submit), `xp_awarded` (0 if already given), `first_completion_bonus`. Unknown category / changed locked value / over income → 400 |
| GET `/api/game/attempts` ✅ | completed games (newest 30), `total_xp`, `best_scores` per level |
| POST `/api/speech-to-text` 🆕 | audio clip → text (backup for phones without Web Speech) |

---

## 7. Build order for this task 🆕

Each step is checked before the next one starts. After each step: what was built, how to try it on a phone, and this file updated.

1. **Backend:** tables, `categories.py`, `money.py`, all routes, pytest tests for the calculations.
2. **Tab bar + Money out view + Add expense** (+ manifest, service worker, icons).
3. **Money in view + Add income.**
4. **Targets tab.**
5. **Arcade tab.** ✅ Budget Challenge
6. **Voice input** (`voice.js`, `expense_parser.py`, `/api/voice/parse-expense`, `/api/speech-to-text`).

---

## 8. External APIs

### Gmail ✅ (sending login codes)
The app sends email through Gmail's normal mail server (SMTP) using an **App Password**. You don't need a Google API key or a Google Cloud project.
1. Turn on **2-Step Verification** for the Gmail account: myaccount.google.com → Security.
2. Go to **myaccount.google.com/apppasswords** → create one (name it e.g. "Finance app") → copy the 16 letters.
3. Put them in `backend/.env` as `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`.
Gmail allows about 500 emails a day, which is plenty for a hackathon.

### OpenAI (speech-to-text backup only, in this task)
| Feature | First choice (free, in the browser) | Backup (our backend calls it) | .env key |
|---|---|---|---|
| **Speech-to-text** | Web Speech API: works in Chrome on Android | **OpenAI** `gpt-4o-mini-transcribe` | `OPENAI_API_KEY` |
| **Understanding "I spent 245 on lunch"** | `expense_parser.py`: simple Python word matching (free) | — | none |

**Why speech needs a backup:** the browser's speech recognition is missing or unreliable in Samsung Internet, Firefox, and on iPhones (especially when the app is installed to the home screen). On those phones, `voice.js` records a short clip and sends it to `/api/speech-to-text`. Python passes it to OpenAI and sends the text back.

Text-to-speech and translation (OpenAI or Google Cloud / DeepL) are **later** features, not part of this task.

### Keys you need to get
0. **`GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`**: needed for login (see above).
1. **`OPENAI_API_KEY`** (optional): platform.openai.com → API keys → Create key; add about $5 of credit. Without it, voice still works in Chrome on Android; other phones show "type it instead".

### `backend/.env.example`
```
# Copy this file to .env and fill in the real values. Never commit .env.
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
OPENAI_API_KEY=
DATABASE_URL=sqlite:///./app.db
```

---

## 9. How to run it

### On your computer
```bash
cd backend
python -m venv venv
venv\Scripts\activate           # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Windows   (Mac/Linux: cp .env.example .env), then add your keys
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Then open **http://localhost:8000/login.html**. FastAPI serves both the app and the API from this one address.

### Run the tests
From the project folder (the one with `backend/` and `tests/`):
```bash
backend\venv\Scripts\python -m pytest tests/backend -q      # Mac/Linux: backend/venv/bin/python -m pytest tests/backend -q
```
Tests use a temporary database and a fake email sender, so they never touch `app.db` or send real emails.

### On your phone
Phones only allow the **microphone, service worker (offline) and "Add to Home Screen"** on **https://** addresses. Plain `http://192.168.x.x` opens the app, but those features stay off.

The easiest fix is a free tunnel, which gives your laptop a temporary https link:
```bash
cloudflared tunnel --url http://localhost:8000     # free, no account needed
```
It prints a link such as `https://something.trycloudflare.com`. Open it on any phone, on any network.

To install the app:
- **Android (Chrome / Samsung Internet):** menu ⋮ → **Install app** / **Add to Home screen**.
- **iPhone (Safari):** Share button → **Add to Home Screen**.

### Test widths
In Chrome on your laptop, press F12 → toggle the device toolbar → check **360px**, **390px** and **430px** wide.
