# PROGRAM_STRUCTURE.md

A short, plain-English map of the app: what it does, where the code lives, and how to run it.
**Update it after any change** to files, features or logic.

## 1. What the app is
A money app for young people (16–25) in Mauritius. It helps them track money in and out, follow a budget style,
save for goals and understand loans. It is a **web app that works like a phone app** (it can be added to the home
screen and opens offline). It works in **English, French and Mauritian Creole**.

There are **4 tabs**: **Money**, **Dashboard** (opens first), **Loans**, **Profile**.

## 2. Features

### Logging in
- Register with a username, an **email** and a strong password (the password meter shows each rule).
- Log in with email + password, then type a **6-digit code** sent by email. The code lasts 5 minutes.
- Sending (`email_sender.py`): **Brevo HTTP API** (`POST https://api.brevo.com/v3/smtp/email`, httpx, 10 s timeout,
  one try) when `BREVO_API_KEY` is set; otherwise **Gmail SMTP** (local development). Same email text either way.
  Any failure → 503 `EMAIL_FAILED`. The code and the API key are never logged.
- 3 wrong passwords lock the account; "Send me a login code" unlocks it.
- Limits stop people guessing codes or flooding inboxes.
- Login is email only. Phone numbers and WhatsApp codes were removed (migration 0010 deleted phone-only accounts
  and the `profiles.phone` column).

### Money tab
- **Month picker** at the top.
- **Summary card**: Left to spend, In, Out, **Saved** (real money put into savings − taken out this month), an
  **encouraging savings message**, and a Needs / Wants / Savings bar that aims at the user's budget style.
- **Money out**: add expenses (one-off, weekly or monthly), Quick add buttons, **📷 Scan bill** (fills the form from
  a photo), a budget per category, fixed bills, latest expenses. The app guesses the category from the note.
- **Money in**: regular income (monthly or weekly, added once) and one-off income.
- **Savings**: total savings, **+ Add to savings / Take out**, this month's entries (tap to edit or delete), monthly
  saving target, safety net (3 × fixed bills) and goals with deadlines, priorities and an inflation estimate.
- **My budget plan** (see below).
- **Financial insights**: a plain check-up of the month, plus optional AI advice (Groq) only when tapped.

### Savings (real money)
| Value | What it is | Changed by |
|---|---|---|
| Total savings (bank balance) | money in savings now | "Update total" (starting balance only) + every Add / Take out |
| Saved this month | money put in − taken out this month | Add to savings / Take out entries dated this month |
| Monthly saving target | the goal per month (own, or 20% of regular income) | "Change" |
| Safety net / a goal | part of total savings set aside | Add / Take out with that place picked |
- Editing or deleting an entry undoes its effect. Nothing can go below 0; a goal never goes above its target.
- "Update total" is NOT counted as saved this month.
- Savings states (`info_status.py`): **missing** (never added) → "You haven't added any savings yet…" + Add button,
  never off plan · **none** or 0 → "No savings this month so far. That's okay…" · below target → "You've saved
  Rs X of your Rs Y goal…" · on target → "You're on track!". Never blaming.

### My budget plan (budget style)
- **Styles** (needs / wants / savings): 50/30/20 (50/30/20) · 60% plan (70/10/20) · Student caps (60/30/10) ·
  **Pay yourself first (50/30/20, saves the most)** · Zero-based (55/25/20) · Debt first (50/30/20, loan repayments
  count as the 20%).
- **Day one**: 4 questions about the user's situation pick a style. First match wins: loan → Debt first, rent →
  60% plan, irregular income → Zero-based, studying → Student caps, otherwise 50/30/20. Any style can be picked here.
- **From real spending** (after 14+ days or 10+ expenses; simple rules, no AI): no income → Zero-based ·
  essentials > 60% of income → Zero-based · otherwise → Pay yourself first. The reason is shown ("Your essentials
  are 68% of your income, so…"). The user accepts it or picks a style by hand.
- **Commitment rules** (checked by the server): the style changes once per calendar month (`style_changed_at`);
  changes start on the 1st of next month (a stricter one may start now); a style that saves less shows what it
  costs, asks why, and needs a second "yes"; wants overspending never unlocks a looser style.
- **Month results are worked out when viewed** (like every summary number, never stored), each against the style
  active in that month (from the plan history). Expenses logged late still count. Streak = months on plan in a row.

### 📷 Scan bill
- In Add expense: a file picker (`accept="image/*" capture="environment"`, no permission pop-up).
- The phone shrinks the photo; the backend checks it (JPG / PNG / WebP by its bytes, max 5 MB) and asks a Groq vision
  model (`GROQ_VISION_MODEL`) for JSON: amount, date, shop, category (checked with Pydantic).
- It only fills in the form: nothing is saved until Save. The photo is never stored or logged.
- Same guards as Insights (no key → friendly message, own daily limit + cooldown). Failure → "Couldn't read this
  bill – type it in instead", the form stays open.

### Dashboard
- Tiles: money available this month, monthly spending (6 months), saving rate (real saving ÷ income), loan payoff,
  monthly recap, money habits score (0–100, not a credit score), savings jars (one per goal). Plain maths, never AI.

### Loans tab
- My current loan (payoff date, interest, extra payments) and "How much can I borrow?" (risk model trained on real
  Lending Club loans + the 40%-of-income rule). Saved loans count in the rest of the app.

### Profile tab
- Account (username, email, occupation, password), weekly budget + badges, **Budget Challenge** game.
- **Delete account** (bottom of the account card): asks for the password, then deletes the account and ALL its
  data (database CASCADE), logs out every device and opens the login page. Cannot be undone.

### Settings (gear icon on every page)
- Theme, language, log out.

### Privacy
- Every money detail is optional: missing information shows "—" and a prompt, never a fake Rs 0.
- Each user only ever sees their own data.

## 3. Where the code lives
```
commitlocal/
├── frontend/                 screens (HTML, CSS, JavaScript)
│   ├── index.html            the app page (all tabs and pop-ups)    login.html/js  log in / register
│   ├── app.js                shared helpers (tabs, pop-ups, money)   api.js         every backend call
│   ├── money-tab.js          Money tab (+ Scan bill, savings message) savings-view.js Savings + entries
│   ├── budget-plan.js        My budget plan                         insights.js    Financial insights
│   ├── dashboard.js          Dashboard     loans-tab.js  Loans      profile-tab.js Profile
│   ├── arcade-tab.js         Budget Challenge                       i18n.js + lang/ en, fr, mfe texts
│   └── service-worker.js     offline copy (bump CACHE_NAME after frontend changes)
├── backend/                  the server (Python, FastAPI)
│   ├── main.py               starts the app        models.py   forms + tables     money.py  money maths
│   ├── budget_plans.py       the styles + references (edit here)
│   ├── savings_entries.py    the ONE place savings totals change (add / take out / undo)
│   ├── info_status.py        provided / none / missing per topic
│   ├── routes/               one file per API part (auth, expenses, savings, plan, goals, ...)
│   ├── services/             month_summary (shared month maths), budget_plan, bill_scan, ai_insights,
│   │                         dashboard, forecast, financial_analysis, inflation
│   ├── game/                 Budget Challenge rules
│   └── migrations/versions/  database changes 0001–0012
└── tests/                    backend (pytest) and frontend (node --test)
```
**Rule:** the maths and every rule live in the backend; the frontend only shows the result.
All month numbers (In, Out, Saved, Left, split, forecast) come from `services/month_summary.build_month_summary`.

## 4. Data
- SQLite on your computer (`backend/app.db`), PostgreSQL (Neon) in production. Money is stored in cents.
- Tables: users, profiles, sessions, otp_codes, income, expenses (+ `weekly`), budgets, savings_settings,
  savings_goals, deposits (savings entries: `kind` deposit / withdrawal, `place` general / safety_net / goal),
  my_loans, info_choices, weekly_budgets, earned_badges, game_attempts, ai_insights, ai_requests (also counts bill
  scans, month = "bill-scan"), plan_history.
- Deleting a user deletes all their rows. The database updates itself (migrations) when the app starts.
- Recent migrations: 0010 phone removal · 0011 plan_history + expenses.weekly · 0012 savings entries (kind, place;
  drops an old plan_results table if a draft created it).

## 5. API
| Area | Routes |
|---|---|
| Auth | POST /api/auth/register, /login, /resend-code, /send-login-code, /verify-code, /logout · GET /api/auth/me · PUT /api/auth/language |
| Profile | GET /api/profile · PUT /api/profile/name, /username, /email, /occupation, /password · DELETE /api/profile (password) |
| Money | GET /api/summary · GET/POST /api/income, PUT/DELETE /api/income/{id} · GET/POST /api/expenses, PUT/DELETE /api/expenses/{id} · GET/POST /api/expenses/quick · GET /api/expenses/suggest-category, /category-keywords · POST /api/expenses/scan-bill · GET/PUT /api/budgets |
| Savings | GET/PUT /api/savings · GET/POST /api/savings/entries, PUT/DELETE /api/savings/entries/{id} · POST /api/savings/safety-net/add-money · GET/POST /api/goals, PUT/DELETE /api/goals/{id}, POST /api/goals/{id}/add-money, GET /api/goals/{id}/inflation-projection · GET /api/inflation/projection |
| Plan | GET /api/plan · POST /api/plan/start/preview, /start, /change · GET /api/plan/preview · DELETE /api/plan/pending |
| Other | GET /api/dashboard, PUT /api/dashboard/weekly-budget · GET /api/forecast · GET /api/info-status, PUT /api/info-choices · GET /api/insights, POST /api/insights/quick, /generate · POST /api/loans/predict · GET/POST /api/my-loans, PUT/DELETE /api/my-loans/{id} · GET /api/game/levels, GET/POST /api/game/attempts, POST /api/game/attempts/{id}/submit |

## 6. Settings (`backend/.env`, copy from `.env.example`)
| Setting | What it does |
|---|---|
| `BREVO_API_KEY`, `EMAIL_FROM`, `EMAIL_FROM_NAME` | send login codes through Brevo (needed on Render; name empty = Pennyworth) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | send login codes through Gmail when `BREVO_API_KEY` is empty (local) |
| `GROQ_API_KEY` (+ `GROQ_MODEL`, `AI_*`) | AI insights (optional) |
| `GROQ_VISION_MODEL`, `BILL_SCAN_DAILY_LIMIT`, `BILL_SCAN_COOLDOWN_SECONDS` | Scan bill (optional; uses `GROQ_API_KEY`) |
| `DATABASE_URL` | empty = SQLite; a PostgreSQL link in production |
| `APP_ENV` | `production` on the server |
| `DEMO_SHOW_OTP` | demo only: shows the login code on screen. Keep `false` |
| `DEMO_TODAY` | demo only: the budget plan pretends today is this date. Ignored in production |

## 7. How to run it
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in your keys
uvicorn main:app --reload --port 8000
```
Open **http://localhost:8000/login.html** (development on your computer; phones use the Render link below).

**Tests** (from `commitlocal`): `backend\venv\Scripts\python -m pytest tests/backend -q` and `node --test tests/frontend`.
Groq, Brevo and Gmail are always faked in tests.

## 8. Deployment (Render + Neon)
- **Live app:** `https://pennyworth.onrender.com/login.html` (service name `pennyworth` in render.yaml; free plan).
  Render never changes an existing service's URL: after the rename, create a new service from the Blueprint, copy
  its secret variables, then delete the old `my-money` service.
- **Config:** `render.yaml` at the top of the repo (the only copy; Render reads it by default): root
  `commitlocal/backend`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT
  --proxy-headers --forwarded-allow-ips "*"`, health check `/health`, `APP_ENV=production`, auto-deploy on push.
- **Same address for app + API:** FastAPI serves `frontend/` (`main.py` mounts it last), so no CORS.
- **Database:** Neon PostgreSQL (`DATABASE_URL`). Alembic migrations (0001–0012) run at every start.
- **Runtime files in git:** `backend/AI_model/loan_risk_model.pkl` + `_card.json`, `data/cpi_mauritius.csv`. Missing
  → the app still starts (40% rule only / "Inflation data unavailable"). The old 58 MB `loan_amount_model.pkl` is
  not used and stays out of git.
- **Email on Render:** the free plan blocks SMTP ports (25/465/587), so Gmail SMTP fails there. Login codes go
  through the Brevo HTTP API instead (`BREVO_API_KEY`).
- **Render variables:** required `DATABASE_URL`, `BREVO_API_KEY`, `EMAIL_FROM`; optional `EMAIL_FROM_NAME`, `GROQ_API_KEY`,
  `GROQ_MODEL`, `GROQ_VISION_MODEL`, `DEMO_SHOW_OTP` (demo only); `APP_ENV` and `PYTHON_VERSION` come from render.yaml.
- **Before every deploy with a new migration:** Neon → Branches → Create branch (e.g. `backup-before-deploy`).
- **Free plan:** sleeps after ~15 min idle (first visit ~30–60 s). Open the link a minute before a demo.
- Full click-by-click guide and fixes: README.md → "Deploy".
