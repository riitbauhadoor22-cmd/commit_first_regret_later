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
| `WHATSAPP_ENABLED`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANG` (+ optional `WHATSAPP_API_VERSION`) | WhatsApp login codes through the Meta WhatsApp Cloud API (optional – see below) |
| `DEMO_SHOW_OTP` | `false`! Only `true` for a demo: shows the login code on screen |
| `GROQ_API_KEY` (+ optional `GROQ_MODEL`, `AI_*` limits) | AI financial insights (optional – without it the app gives "Quick insights (no AI)") |
| `DATABASE_URL` | Leave empty for SQLite; set a PostgreSQL URL (Supabase/Neon) when deploying |

Never commit `.env`.

### WhatsApp login codes
A login code is needed at **every** login (none at registration). Email-only accounts get it by email, phone-only accounts on WhatsApp, accounts with both get it by email and can switch on the code screen ("Send code by: Email / WhatsApp").

**Set it up (Meta WhatsApp Cloud API, free test mode):**
1. Create a Meta developer account at **developers.facebook.com** → **My Apps → Create app** → type **Business** (you also need a Meta Business portfolio; the wizard offers to make one).
2. In the app dashboard, **add the WhatsApp product**. Meta gives you a free **test phone number** to send from.
3. **WhatsApp → API Setup**: click **Generate access token** → this *temporary* token lasts less than 24 hours (fine to try it). For a token that doesn't expire: **Business Settings → Users → System users** → add a system user, give it your app and WhatsApp account (full control), **Generate token** with the permissions `whatsapp_business_messaging` + `whatsapp_business_management` (+ `business_management`).
4. On the same API Setup page copy the **Phone number ID** (a long number shown under the test number — not the phone number itself).
5. Under **To** → **Manage phone number list**: add the WhatsApp numbers that will log in (each gets a verification code on WhatsApp to confirm). *Test mode only sends to these numbers — Meta allows up to 5 (limit not re-checked in Meta's current docs).*
6. **WhatsApp Manager → Message templates → Create template** → category **Authentication** → **Copy code** button (optionally the security sentence and an expiry footer, e.g. 5 minutes) → language e.g. English (`en_US`) → submit and **wait until it is Approved**. Note its exact name.
7. `backend/.env`: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANG` (the template's language, default `en_US`), optional `WHATSAPP_API_VERSION` (default `v27.0`), then **`WHATSAPP_ENABLED=true`**. **Restart the server.**
- What is sent: `POST https://graph.facebook.com/<version>/<PHONE_NUMBER_ID>/messages` with `Authorization: Bearer <token>` and a `template` message whose **body** parameter and **copy-code button** (`sub_type: url`, `index: "0"`) parameter are both the code — Meta's documented format for authentication templates.
- Test-mode limits: only the numbers added in step 5 receive messages. Real users need a verified business, your own phone number and Meta's per-message pricing for authentication messages.
- If something is wrong the user only sees the translated "We couldn't send the code on WhatsApp right now"; the **server log** shows Meta's status and error (e.g. `131030` = number not in the test list, `132001` = template name / language doesn't exist, `190` = token expired). The code and the token are never logged.
- **`DEMO_SHOW_OTP`** must stay **`false`** outside a demo: `true` shows the code on the code screen (after a correct password), so the phone / inbox is no longer needed.

Meta docs used: developers.facebook.com/documentation/business-messaging/whatsapp/get-started and .../whatsapp/templates/authentication-templates/copy-code-button-authentication-templates (checked Nov 2026).

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

## Live demo (hackathon)

- Link: https://bd7937899f781d.app.lhr.life (temporary tunnel from the team laptop via localhost.run; works while the laptop server is running)
- QR code: [demo-qr.png](demo-qr.png)
- Demo mode: the login code is also shown on screen (DEMO_SHOW_OTP=true) so the demo never gets stuck.
