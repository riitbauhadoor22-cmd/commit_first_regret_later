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
pip install -r requirements.txt
copy .env.example .env        (then fill in the values below)
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Open **http://localhost:8000/login.html**. The database (`backend/app.db`) and its tables are created automatically on first start.

To open it on a phone: `cloudflared tunnel --url http://localhost:8000` and open the `https://…trycloudflare.com/login.html` link it prints.

### `backend/.env`
| Variable | Needed for |
|---|---|
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Emailing login codes (Gmail App Password) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` | WhatsApp login codes (optional) |
| `GROQ_API_KEY` (+ optional `GROQ_MODEL`, `AI_*` limits) | AI financial insights (optional – without it the app gives "Quick insights (no AI)") |
| `DATABASE_URL` | Leave empty for SQLite; set a PostgreSQL URL (Supabase/Neon) when deploying |

Never commit `.env`.

## Tests
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
