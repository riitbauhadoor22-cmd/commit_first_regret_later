# Finance PWA

I acknowledge the use of AI during the coding and brainstorming process.

A money app for young people in Mauritius (16–25). It works in any phone browser, can be added to the home screen and still opens offline. All amounts are in rupees (Rs). Available in **English, French and Kreol Morisien**.

## What it does

| Tab | Features |
|---|---|
| **Dashboard** | Available money, spending, saving rate, financial health score, monthly recap, savings jars |
| **Money** | Money in (regular + one-off income), Money out (expenses by category with budgets, fixed monthly bills), Savings (bank balance, safety net, monthly saving target, goals). 50/30/20 split, spending forecast, auto-categorised expenses, Financial insights (rule-based, optional AI via Groq) |
| **Loans** | *My current loan*: payoff date, interest, balance graph. *Can I afford a loan?*: risk model trained on real loan outcomes + the 40% debt-to-income rule |
| **Profile** | Account details, weekly budget + badges, **Budget Challenge** game (3 fictional levels, XP) |
| **Settings** (gear icon) | Theme, language, log out |

Savings goals also show an **inflation-adjusted cost** using the official Statistics Mauritius CPI.

## Real data used
- **Statistics Mauritius CPI** (Oct 2025 – Oct 2026, by category) – `data/cpi_mauritius.csv`, rebuilt with `python scripts/build_cpi_csv.py`
- **Lending Club loans** (Kaggle "All Lending Club loan data", 825,536 finished loans 2007–2015) – risk model in `backend/AI_model/loan_risk_model.pkl`. The 1.2 GB CSV is not in git; download it to `backend/DATA/lending_club/loan.csv` to retrain.

## Run it

```
cd commitlocal\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt   (app + pytest; the server only needs requirements.txt)
copy .env.example .env        (then fill in the values below)
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open **http://localhost:8000/login.html**. The database (`backend/app.db`) and its tables are created automatically on first start.

This is for development on your computer. To use it on a phone, use the Render link (see **Deploy** below).

### `backend/.env`
| Variable | Needed for |
|---|---|
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Emailing login codes (Gmail App Password) |
| `DEMO_SHOW_OTP` | `false`! Only `true` for a demo: shows the login code on screen |
| `GROQ_VISION_MODEL`, `BILL_SCAN_*` | Scan bill (optional, uses `GROQ_API_KEY`; Groq vision models are preview models) |
| `DEMO_TODAY` | Empty! Demo only (ignored in production): the budget plan pretends today is this date, e.g. `2026-12-01` to "jump" to next month |
| `GROQ_API_KEY` (+ optional `GROQ_MODEL`, `AI_*` limits) | AI financial insights (optional – without it the app gives "Quick insights (no AI)") |
| `DATABASE_URL` | Leave empty for SQLite; set a PostgreSQL URL (Supabase/Neon) when deploying |
| `APP_ENV` | `production` on the server (Secure cookies, HSTS, no `/docs`); empty = development |

Never commit `.env`.

## Deploy (Render + Neon) — the fixed link
The app runs on Render's free plan at a fixed `https://<name>.onrender.com` link. `render.yaml` (top of the repo, the
only copy) tells Render how: root `commitlocal/backend`, build `pip install -r requirements.txt`, start
`uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*"`, health check `/health`,
`APP_ENV=production`. FastAPI serves the API and the frontend from the same address (no CORS). The database tables
are updated by the Alembic migrations every time the app starts.

### Environment variables (Render dashboard → the service → Environment)
| Variable | Required? | What it is |
|---|---|---|
| `DATABASE_URL` | **required** | Neon connection string (`postgresql://…?sslmode=require`) |
| `GMAIL_ADDRESS` | **required** | the Gmail account that emails the login codes |
| `GMAIL_APP_PASSWORD` | **required** | its 16-letter Gmail App Password (Google account → Security → App passwords) |
| `APP_ENV` | set by render.yaml | `production` (Secure cookies, HSTS, no `/docs`, demo date switch off) |
| `PYTHON_VERSION` | set by render.yaml | `3.14.0` (same as the venv the app is tested with) |
| `GROQ_API_KEY` | optional | AI insights + Scan bill. Empty = "Quick insights (no AI)" and "Scanning isn't available" |
| `GROQ_MODEL` | optional | AI insights model, empty = `openai/gpt-oss-20b` |
| `GROQ_VISION_MODEL` | optional | Scan bill model, empty = `qwen/qwen3.8-27b` (a Groq preview model) |
| `DEMO_SHOW_OTP` | optional | empty = off. `true` only during a live demo (shows the login code on screen) |
| `AI_*`, `BILL_SCAN_*` | optional | limits, see `backend/.env.example` (defaults are fine) |
Never set `DEMO_TODAY` on Render (it is ignored in production anyway).

### Step by step (first time)
1. **Back up Neon.** neon.tech → your project → **Branches** → **Create branch** → name `backup-before-deploy`,
   from `main`, "Current point in time" → **Create**. Wait until it is in the list.
2. **Push to GitHub.** Commit your changes (include the new files: `git status` must not show anything you need as
   `??`) and `git push`.
3. **Render.** render.com → sign in with GitHub → **New +** → **Blueprint** → pick this repo → Render finds
   `render.yaml` → it shows the service `my-money` (free plan) → fill in the `sync: false` variables from the table
   above (at least `DATABASE_URL`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`) → **Apply**.
   (No Blueprint? **New +** → **Web Service** → this repo → Root Directory `commitlocal/backend`, Runtime Python, the
   build / start commands above, Instance type **Free**, health check path `/health`, add the variables incl.
   `APP_ENV=production` and `PYTHON_VERSION=3.14.0`.)
4. **Watch the deploy.** The service → **Logs**. The build installs the packages; then you should see
   `App mode: production` and `AI insights: ON` (or `OFF` without a Groq key). The migrations (up to 0012) run
   quietly right after: no red error + `Application startup complete` = they worked (a failed migration stops the
   start-up with an error). The service turns **Live**.
5. **Try it on your phone.** Open `https://<name>.onrender.com/login.html` → Register → log in with the emailed
   code → add an expense → Money → Savings → **+ Add to savings** → Add expense → **📷 Scan bill**.
6. **Install it.** Android (Chrome / Samsung Internet): menu ⋮ → **Install app** / **Add to Home screen**.
   iPhone (Safari): Share → **Add to Home Screen**.
7. **Later changes.** Commit and push to the same branch: Render redeploys by itself (`autoDeploy`). Back up Neon
   first when the push contains a new migration. Render → **Manual Deploy** redeploys without a push.

### Free plan limits
- The service **sleeps after about 15 minutes** without visitors; the next visit waits ~30–60 s while it wakes up.
  Before a demo, open the link a minute early (or keep a tab refreshing it). Paid plans don't sleep.
- One small instance: the in-memory limits (login tries, codes, AI cooldowns) reset when it restarts.
- Neon's free database also pauses when idle (the first request after a pause takes a second or two longer).

### If the deploy breaks
| You see | Fix |
|---|---|
| Build fails installing a package | Check the Python version in the logs; set `PYTHON_VERSION` to a version Render offers (e.g. `3.13.1`) |
| `could not connect` / SSL errors at start | `DATABASE_URL` must be Neon's full string with `?sslmode=require` |
| A migration error at start | Read the Alembic error in Logs; restore from the `backup-before-deploy` branch if data changed |
| "We couldn't send the email" when logging in | Check `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` (an App Password, not the normal password) |
| Health check fails | Logs show why the app didn't start; `/health` only answers once start-up (migrations) is done |
| Old screens on the phone | Pull to refresh / reopen: the offline copy updates when `CACHE_NAME` changes |

Rate limits (login, register, codes) are kept in memory: fine for one free instance; they reset when Render restarts it.

### Budget plans
Money tab → **My budget plan**: day one, 4 questions about the user's situation pick a style (50/30/20, 60% plan, Student caps, Pay yourself first, Zero-based, Debt first; `backend/budget_plans.py`). After 14+ days or 10+ expenses the app suggests a style from real spending with simple rules (`backend/services/budget_plan.py`). The API enforces the commitment rules (`backend/routes/plan.py`): one change per calendar month, changes start on the 1st of next month, a style that saves less needs a reason and a second confirm, and overspending on wants never unlocks a looser style. Month results are worked out when viewed, against the style that was active that month.

### Real savings and Scan bill
"Saved" is real money: **+ Add to savings** / **Take out** entries (Money → Savings) move total savings and the safety net or goal picked (`backend/savings_entries.py`); "Update total" only sets the starting balance. **📷 Scan bill** in Add expense reads a photo with a Groq vision model (`GROQ_VISION_MODEL`) and only fills in the form; photos are never stored.

### Login codes
A 6-digit login code is emailed at **every** login (none at registration).
**`DEMO_SHOW_OTP`** must stay **`false`** outside a demo: `true` shows the code on the code screen (after a correct password), so the inbox is no longer needed.

## Tests
Install `backend/requirements-dev.txt` first (adds pytest).
From `commitlocal`:
```
backend\venv\Scripts\python -m pytest tests/backend -q
node --test tests/frontend
```

## More
- `PROGRAM_STRUCTURE.md` – how the code is organised, every route and calculation
- `DECISION_LOG.md` – the key decisions and why
- Retrain the loan risk model: `backend\venv\Scripts\python backend\train_loan_risk_model.py --input backend\DATA\lending_club\loan.csv --out-dir backend\AI_model`

*Estimates only – not financial advice.*

## Live demo (hackathon)

- Link: `https://<name>.onrender.com/login.html` (Render, fixed link; see `web_app_link.txt`). Open it a minute before
  the demo so the free service is awake.
- QR code: [demo-qr.png](demo-qr.png) — make a new one for the Render link after the first deploy.
- Demo mode: set `DEMO_SHOW_OTP=true` in Render's Environment only for the live demo (the login code is also shown on
  screen), then set it back to empty / `false`.
