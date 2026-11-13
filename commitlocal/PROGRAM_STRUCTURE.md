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

The app has **3 tabs** in a bottom tab bar: **Money**, **Targets**, **Arcade**.

**Status:** ✅ Login + registration is built. ✅ Step 1 (backend for the 3 tabs), ✅ step 2 (tab bar, Money out view, Add expense, PWA files), ✅ step 3 (Money in view, Add income), ✅ step 4 (Targets tab) and ✅ step 5 (Arcade placeholder) are built. ⏸ Step 6 (voice) is on hold for now: the mic button just opens Add expense. All amounts are in rupees, shown as **Rs**.

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
│   ├── index.html              ← ✅ the app: 3 tab pages, bottom tab bar, Add expense / Add income / other pop-up screens
│   ├── login.html              ← ✅ Login / Register tabs, "enter your code" box, "account locked" box
│   ├── login.js                ← ✅ tabs, live password strength meter, calls /api/auth/...
│   ├── style.css               ← ✅ colours, fonts, cards, tab bar, progress bars (mobile-first, 360 / 390 / 430 px)
│   ├── api.js                  ← ✅ every call to our backend (fetch) lives here, in one place
│   ├── app.js                  ← ✅ login check, log out, tab switching (each tab reloads its numbers when opened), money formatting ("+Rs 1,200"), open/close pop-ups,
│   │                              short messages (toasts), registers the service worker (replaced home.js, now deleted)
│   ├── money-tab.js            ← ✅ draws the Money tab: Money out (quick-add chips, budgets, fixed bills, See all),
│   │                              Money in (regular + one-off income); Add expense, Add income and Set budget forms
│   ├── targets-tab.js          ← ✅ draws the Targets tab; New/Edit goal form; Add money (goal or safety net);
│   │                              update bank balance; change the monthly target (or go back to 20%)
│   ├── voice.js                ← 🆕 microphone → text (Web Speech API, or record audio for /api/speech-to-text)
│   ├── manifest.json           ← ✅ app name, icons, colours, start page, "standalone" (makes it installable)
│   ├── service-worker.js       ← ✅ keeps a copy of the app files: internet first, saved copy when offline (never /api/)
│   ├── icons/                  ← ✅ icon-192.png, icon-512.png, apple-touch-icon.png (180×180)
│   ├── lang.js, lang/          ← (later) other languages
│   └── offline.js              ← (later) queue expenses added offline
│
└── backend/                    ← Python + FastAPI: all logic, data and API keys
    ├── main.py                 ← ✅ starts FastAPI, connects all the routes, serves the frontend folder
    ├── database.py             ← ✅ opens SQLite (finance.db) and creates the tables (new money tables added)
    ├── models.py               ← ✅ shape of incoming data (Pydantic): login forms + Income, Expense, Budget, Savings, Goal, Deposit forms
    ├── security.py             ← ✅ password rules, bcrypt (14 rounds), 6-digit codes, session tokens
    ├── email_sender.py         ← ✅ emails the 6-digit code through Gmail
    ├── categories.py           ← ✅ the fixed lists: categories (+ default Need/Want), income types, frequencies
    ├── money.py                ← ✅ ALL the maths, as plain functions with no database (easy to test) — see section 3
    ├── expense_parser.py       ← 🆕 "I spent 245 on lunch" → {amount: 245, category: "Food & drinks", note: "lunch"}
    ├── routes/
    │   ├── auth.py             ← ✅ /api/auth (+ ✅ `require_user`: 401 if not logged in)
    │   ├── summary.py          ← ✅ /api/summary: everything the Money tab's dark card + category rows need
    │   ├── income.py           ← ✅ /api/income: list, add, edit, delete
    │   ├── expenses.py         ← ✅ /api/expenses: list, add, edit, delete; quick-add chips
    │   ├── budgets.py          ← ✅ /api/budgets: list, set a category's monthly limit
    │   ├── savings.py          ← ✅ /api/savings: bank balance, monthly target, safety net (+ add money to it)
    │   ├── goals.py            ← ✅ /api/goals: list (with status), add, edit, delete, add money
    │   └── voice.py            ← 🆕 /api/voice/parse-expense and /api/speech-to-text (calls OpenAI)
    ├── tests/
    │   ├── conftest.py         ← ✅ test setup: temporary database + fake logged-in user
    │   ├── test_money.py       ← ✅ pytest tests for every calculation in money.py
    │   ├── test_parser.py      ← 🆕 pytest tests for expense_parser.py
    │   └── test_routes.py      ← ✅ a few tests through the API (temporary test database, fake logged-in user)
    ├── requirements.txt        ← ✅ now also has: pytest, httpx (tests + calling OpenAI), python-multipart (audio upload)
    ├── .env.example            ← names of the keys, with no real values (safe to commit)
    ├── .env                    ← YOUR real keys (never committed, never sent to the browser)
    └── finance.db              ← the SQLite database file (created automatically, not committed)
```

**Rule of thumb:** if logic *can* run in Python, it goes in `backend/`. JavaScript only shows screens, sends forms, uses the microphone, and caches files for offline.

---

## 3. How the logic works

### Login and registration ✅
1. **Register** → name, email, password twice → the strength meter turns red→green and ticks each rule → Python checks the rules again → the email is saved in lowercase (so `Asha@X.com` = `asha@x.com`) → the password is saved as a **bcrypt hash (14 rounds)**.
2. **Log in, step 1** → email + password → if correct, Python emails a **6-digit code** through Gmail (it expires in **5 minutes**).
3. **Log in, step 2** → the user types the code → if correct, Python creates a session and puts it in an **HttpOnly cookie** (JavaScript can't read it) → the user is logged in for 7 days.
4. **3 wrong passwords** → the account is **locked**, and even the right password won't work → the user taps **"Send me a login code"** → enters the emailed code → logged in **and unlocked**.
5. **Safety limits:** a code dies after 5 wrong guesses; a new code replaces the old one; a new unlock code can only be sent once every 60 seconds.

### Every money route ✅
- Reads the session cookie → finds the user → **401 if not logged in** (the app then goes to `login.html`).
- Every row has a `user_id`. Every SQL query has `WHERE user_id = ?`, so you can only see or change **your own** rows (someone else's id → 404).
- Amounts must be **more than 0 and at most 10,000,000**, rounded to 2 decimals. Dates are `YYYY-MM-DD`, months `YYYY-MM`.

### Fixed lists (`categories.py`) ✅
| Category | Default kind |
|---|---|
| Groceries, Transport, Bills, Utilities, Other | Need |
| Food & drinks, Shopping, Subscriptions, Fun & outings | Want |

- Income types: Salary, Allowance, Side hustle, Scholarship, Other.
- Income frequency: `monthly`, `weekly`, `one-off`.
- Goal priority: `1` = High, `2` = Medium, `3` = Low.

### The maths (`money.py`, all on the backend) ✅
"This month" means the month picked at the top of the Money tab (default: the current month).

1. **Monthly income** = monthly incomes + weekly incomes × 52 ÷ 12 + one-offs dated this month.
   Monthly/weekly incomes count in every month **from their start date's month onwards**.
2. **Repeating items are never copied.** A regular income or fixed bill is one row; it is simply counted in every month from its date onwards.
3. **Spent this month** = fixed bills (from their start month onwards) + everyday expenses dated this month.
4. **Saved this month** = deposits dated this month (goals + safety net).
5. **Left to spend** = monthly income − spent − saved.
6. **Needs % / Wants % / Savings %** = needs total, wants total, saved ÷ monthly income × 100 (0 if there is no income). Shown next to "aim 50 · 30 · 20".
7. **Category rows** (Everyday spending card) = everyday expenses this month per category, with that category's budget and its default Need/Want (the Add expense grid is built from this list, so the categories live only in Python). Over budget → `over_by` = spent − budget. *Fixed bills are not in these rows — they have their own card.*
8. **Monthly saving target** = `savings.monthly_target` if the user set one, otherwise **20% of regular income** (monthly + weekly × 52 ÷ 12, no one-offs).
9. **Safety net target** = 3 × the total of fixed monthly bills. % reached = safety_net_saved ÷ target × 100 (max 100).
10. **Goal "needs per month"** = (target − saved) ÷ months left. Months left = months from this month to the deadline's month, **at least 1**.
11. **Goal status:** go through goals by priority (High first; same priority → earlier deadline first). Give each goal money from the monthly saving target until it runs out. A goal that gets at least what it needs = **On track**, otherwise **Needs more**. A finished goal (saved = target) = **Done**.
12. **Too-many-goals warning:** if all goals together need more per month than the saving target → "Your goals need Rs X a month, but you save Rs Y. Push a date back or focus on one goal first."
13. **Adding money to a goal** → save a deposit, add it to `goal.saved_amount` and to `savings.bank_balance`. The amount must be positive and can't push saved above target (it is capped at what's still needed). Adding to the **safety net** works the same, using `safety_net_saved` (deposit with empty goal_id); the safety net has no upper limit. Editing a goal can't set its target below what's already saved. Deleting a goal deletes its deposits, but the money stays in the bank balance.
14. **Bank bar** (Targets dark card) = bank_balance split into: safety net, one segment per goal (its saved amount), and the rest ("free").
15. **Quick add chips** = everyday expenses from the last 30 days, grouped by (note, amount), the 4 most frequent (ties → most recent). One tap → `POST /api/expenses/quick` saves the same expense again with today's date and `source = "quick"`.

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

Colours: background `#F6F7F9`, white cards (20px corners), dark summary card `#14161A`, active tab blue `#2F4BC0`.
**Income = green `#237032` with "+"**, **expenses = orange `#A34A00` with "−"** — everywhere. On the dark card, lighter versions of the same green and orange are used so they are readable. Amounts use Indian grouping (Rs 1,50,000); the 3 small numbers on the dark card are rounded to whole rupees so they fit at 360px.
Fonts: **Space Grotesk** (headings), **Inter** (text), from Google Fonts. Every button is at least **44px** tall.
A small **Log out** button sits at the top right of each tab.

### Tab 1: Money ✅
- Title "Money" + month picker (‹ November 2026 ›).
- **Dark card:** big "Left to spend this month"; small In (+green) · Out (−orange) · Saved; Needs/Wants/Savings bar + "aim 50 · 30 · 20".
- Switch **[Money in] [Money out]** — Money out shows first.
- **Money out:**
  1. *Everyday spending* — mic button, "+ Add expense", Quick add chips ("Bus Rs 38"), one row per category: spent / budget + bar. Over → orange-red bar + "⚠ Over budget by Rs X". No budget → spent + "Set budget" link (opens a small box to type the limit). With a budget → "Edit" link under the bar (change or remove it). The mic button opens Add expense for now; listening is added in step 6.
  2. *Fixed monthly* — number of bills, total, bill names as small tags, "View or edit bills" → full list (tap to edit / delete) + "+ Add fixed bill".
  3. *Recent* — last 3 expenses of the month + "See all" → full list of the month (edit / delete).
- **Money in:**
  1. *Regular income* — monthly / weekly incomes, each with an "Auto" tag (weekly ones also show "≈ Rs X a month"), "+ Add income". Tap one to edit or delete it.
  2. *One-off this month* — gifts, freelance, prizes, with "+ Add one-off" (opens Add income with One-off picked).
  3. Tip: "You only add regular income once. After that it's added every month."
- **Add expense** screen (also used to edit, with a Delete button): big Rs amount, "Say it" button (hidden until step 6), category grid, Need/Want toggle (pre-picked from the category, can be changed), note, date (today), "Repeats every month" (= fixed bill), Save.
- **Add income** screen (also used to edit, with a Delete button): name, type (buttons), amount, how often (Monthly / Weekly / One-off), date ("Starts on" for repeating income, "Date received" for a one-off).
- Deleting a regular income or a fixed bill asks first, because it is removed from every month, including past ones.
- If a form has a problem, the message appears above Save and the screen scrolls to it.

### Tab 2: Targets ✅
1. **Dark card:** "Saved in your bank" ("Update" to type it in) + bank bar (safety net + one colour per goal + free), with a legend. Each goal card has a dot in the same colour as its part of the bar.
2. **Monthly saving:** target per month ("Change" to type your own, or "Use 20% of my regular income" to go back) + bar + "Rs 2,500 of Rs 3,700 put away this month".
3. **Safety net:** target = 3 × fixed bills, % reached, "+ Add money". No fixed bills yet → a hint to add them in Money → Fixed monthly.
4. **Goals** + "+ New goal" (listed in priority order): name, deadline, priority, progress bar, "saved of target", "Needs Rs X a month", tag (On track / Needs more / Done), "Edit" (change or delete) and "+ Add money" (hidden when Done). If you add more than a goal still needs, only what it needs is added and the message says so.
5. **Warning box** when goals need more than the saving target (logic step 12).

### Tab 3: Arcade ✅ (placeholder only)
Dark "Coming soon" card ("Challenges and mini-games to help you hit your goals will live here.") + 4 dashed boxes [Game 1]–[Game 4] in a 2 × 2 grid. Only HTML + CSS for now: no JS, no backend.

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
 │                               │          │  database.py ──► finance.db  │
 │ Free browser feature:         │          │                              │
 │  • Web Speech API (mic)       │          │  routes/voice.py ────────────┼──► OpenAI (speech-to-text,
 └───────────────────────────────┘          │  .env (API keys live ONLY here)     only if the browser can't)
                                            └──────────────────────────────┘
```

The browser **never** talks to OpenAI directly, and it never sees a key. It only calls our own `/api/...` addresses.

---

## 6. Data stored for each item

Saved in **SQLite** (one file, `backend/finance.db`), the same database the login uses. Money tables are created in `database.py` next to the login tables. **Every money table has `user_id`.**

### User ✅
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 1 | created automatically |
| full_name | text | "Asha Rao" | 1–100 characters |
| email | text | "asha@gmail.com" | unique, always lowercase |
| password_hash | text | "$2b$14$…" | bcrypt hash, never the real password |
| failed_attempts | number | 0–3 | wrong passwords in a row |
| is_locked | 0 / 1 | 0 | 1 after 3 wrong passwords |
| created_at | unix time | 1763020800 | set automatically |

### Login code (otp_codes) ✅
| Field | Notes |
|---|---|
| id, user_id | which user the code is for |
| code_hash | SHA-256 of the 6-digit code (the real code is only in the email) |
| expires_at | 5 minutes after it was made |
| tries | wrong guesses so far (max 5) |
| used | 1 = used, replaced or blocked |
| created_at | used for the 60-second resend wait |

### Session ✅
| Field | Notes |
|---|---|
| token_hash | SHA-256 of the cookie value |
| user_id | who is logged in |
| expires_at | 7 days after login |

### Income (`income`) ✅
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 1 | created automatically |
| user_id | number | 1 | owner |
| name | text | "Part-time job" | 1–60 characters |
| type | text | "Salary" | one of the income types |
| amount | number | 8000.00 | > 0, ≤ 10,000,000 |
| frequency | text | "monthly" | monthly / weekly / one-off |
| date | date | 2026-11-01 | start date (repeating) or date received (one-off) |

### Expense (`expenses`) ✅
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 7 | created automatically |
| user_id | number | 1 | owner |
| amount | number | 245.00 | > 0, ≤ 10,000,000 |
| category | text | "Food & drinks" | one of the 9 categories |
| kind | text | "want" | need / want (default comes from the category) |
| note | text | "lunch" | optional, up to 100 characters |
| date | date | 2026-11-13 | defaults to today; for a fixed bill = the first month it counts |
| is_fixed | 0 / 1 | 0 | 1 = repeats every month (fixed bill) |
| source | text | "typed" | typed / voice / quick |

### Budget (`budgets`) ✅ — replaces the old planned Budget table
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 1 | created automatically |
| user_id | number | 1 | owner |
| category | text | "Food & drinks" | one budget per user per category |
| monthly_limit | number | 3000.00 | > 0; the same limit every month |

### Savings (`savings`) ✅ — one row per user, made the first time it's needed
| Field | Type | Example | Notes |
|---|---|---|---|
| user_id | number | 1 | owner (also the key) |
| bank_balance | number | 12000.00 | ≥ 0, the user can type it in |
| monthly_target | number or empty | 3700.00 | empty = use 20% of regular income |
| safety_net_saved | number | 4000.00 | grows with safety-net deposits |

### Goal (`goals`) ✅
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 2 | created automatically |
| user_id | number | 1 | owner |
| name | text | "New phone" | 1–60 characters |
| target_amount | number | 15000.00 | > 0 |
| saved_amount | number | 4500.00 | starts at 0; never above target |
| deadline | date | 2027-03-01 | required (needed for "Needs Rs X a month") |
| priority | number | 1 | 1 = High, 2 = Medium, 3 = Low |

### Deposit (`deposits`) ✅
| Field | Type | Example | Notes |
|---|---|---|---|
| id | number | 5 | created automatically |
| user_id | number | 1 | owner |
| goal_id | number or empty | 2 | empty = safety net |
| amount | number | 500.00 | > 0 |
| date | date | 2026-11-13 | today |

Deleting a goal deletes its deposits too.

**Calculated, not stored** (worked out in `money.py` each time): monthly income, spent, saved, left to spend, the 3 percentages, category spending, monthly saving target (when empty), safety net target, goal needs-per-month and status, quick-add chips.

### API addresses
All money routes need you to be logged in (401 otherwise).

| Method + address | What it does |
|---|---|
| POST `/api/auth/register` ✅ | create an account |
| POST `/api/auth/login` ✅ | check the password → email a code (423 = locked) |
| POST `/api/auth/send-login-code` ✅ | locked account → email a code |
| POST `/api/auth/verify-code` ✅ | check the code → log in (+ unlock) → set cookie |
| GET `/api/auth/me` ✅ | who is logged in (401 if nobody) |
| POST `/api/auth/logout` ✅ | log out |
| GET `/api/summary?month=YYYY-MM` ✅ | income, spent, saved, left to spend, %s, category rows (spent / budget / over_by), fixed bills, last 3 expenses |
| GET `/api/income?month=YYYY-MM` ✅ | regular incomes + one-offs of that month (each with `per_month`), and the list of income types |
| POST `/api/income` ✅ | add an income |
| PUT / DELETE `/api/income/{id}` ✅ | edit / delete an income |
| GET `/api/expenses?month=YYYY-MM` ✅ | all expenses of that month (for "See all") + fixed bills |
| POST `/api/expenses` ✅ | add an expense (typed or voice) |
| PUT / DELETE `/api/expenses/{id}` ✅ | edit / delete an expense |
| GET `/api/expenses/quick` ✅ | top 4 quick-add chips |
| POST `/api/expenses/quick` ✅ | log a chip again with today's date |
| GET `/api/budgets` ✅ | the user's budgets |
| PUT `/api/budgets` ✅ | set one category's limit `{category, monthly_limit}` (empty limit = remove it) |
| GET `/api/savings` ✅ | bank balance, monthly target (+ this month's progress), safety net target / saved / %, bank bar segments |
| PUT `/api/savings` ✅ | update bank balance and/or monthly target |
| POST `/api/savings/safety-net/add-money` ✅ | add money to the safety net |
| GET `/api/goals` ✅ | goals with needs-per-month + status, total needed, warning text (or none) |
| POST `/api/goals` ✅ | add a goal |
| PUT / DELETE `/api/goals/{id}` ✅ | edit / delete a goal |
| POST `/api/goals/{id}/add-money` ✅ | add money to a goal |
| POST `/api/voice/parse-expense` 🆕 | text → suggested `{amount, category, kind, note}` (not saved) |
| POST `/api/speech-to-text` 🆕 | audio clip → text (backup for phones without Web Speech) |

---

## 7. Build order for this task 🆕

Each step is checked before the next one starts. After each step: what was built, how to try it on a phone, and this file updated.

1. ✅ **Backend:** tables, `categories.py`, `money.py`, all routes, pytest tests for the calculations (30 tests pass).
2. ✅ **Tab bar + Money out view + Add expense** (+ manifest, service worker, icons).
3. ✅ **Money in view + Add income.**
4. ✅ **Targets tab.**
5. ✅ **Arcade tab.**
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
```bash
cd backend
venv\Scripts\activate
python -m pytest
```

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
