# Decision log

The key decisions behind the app, in order. Times are Mauritius time.

| # | When | Decision | Why |
|---|---|---|---|
| 1 | 2026-11-13 18:00 | **FastAPI backend + plain HTML/CSS/JS Progressive Web App** | Opens in any phone browser, installable, works offline; simple for the whole team to work on |
| 2 | 2026-11-13 19:30 | **Login = password + 6-digit code** (email, or WhatsApp for phone-only accounts); 3 wrong passwords lock the account | A money app needs more than a password |
| 3 | 2026-11-13 20:45 | **Secure database design**: SQLAlchemy + Alembic, money stored in cents, UUID ids, every query filtered by the logged-in user | No rounding errors, no guessable ids, users can never see each other's data; same code runs on SQLite now and PostgreSQL later |
| 4 | 2026-11-14 01:00 | **Three languages: English, French, Kreol Morisien** – the backend sends error codes, the app translates them | Built for young Mauritians; all text in one place |
| 5 | 2026-11-14 01:50 | **Real data only**: inflation on savings goals uses the official Statistics Mauritius CPI | Project requirement – a real, existing dataset must power a feature |
| 6 | 2026-11-14 02:40 | **Budget Challenge game** with fictional scenarios, scored on the server, XP once per game | Teaches budgeting without touching the user's real money |
| 7 | 2026-11-14 02:55 | **Loan risk model trained on 825,536 real Lending Club loans** (AUC 0.705); final answer = the lower of the AI estimate and the 40% debt-to-income rule; the old synthetic model was removed | No public Mauritian loan dataset; ratios work in any currency; the rule keeps answers safe |
| 8 | 2026-11-14 07:10 | **Smart features without AI**: spending forecast and auto-categorising (Mauritian shop names + the user's own history); AI insights are optional, with rule-based "Quick insights" as fallback | Works offline, free, explainable; no dead buttons when the AI key is missing |
| 9 | 2026-11-14 08:00 | **Security hardening** before the demo: no user enumeration, cap on code guesses, security headers (CSP), integrity check on Chart.js | The app is public through a Cloudflare tunnel |
| 10 | 2026-11-14 08:55 | **Three separate savings values**: bank balance (what you have), monthly saving target (the plan), saved this month (= the target). One shared function calculates the month summary for every page | The numbers used to contradict each other (e.g. "Rs 2,000 of Rs 100 saved") |
