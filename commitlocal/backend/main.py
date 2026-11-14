# main.py — starts the FastAPI server: brings the database tables up to date (Alembic), connects the API routes, serves the frontend.
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from database import create_tables
from errors import add_error_handlers
from routes.auth import router as auth_router
from routes.budgets import router as budgets_router
from routes.dashboard import router as dashboard_router
from routes.expenses import router as expenses_router
from routes.game import router as game_router
from routes.goals import router as goals_router
from routes.income import router as income_router
from routes.info import router as info_router
from routes.insights import router as insights_router
from routes.inflation import router as inflation_router
from routes.loans import router as loans_router
from routes.my_loans import router as my_loans_router
from routes.profile import router as profile_router
from routes.savings import router as savings_router
from routes.summary import router as summary_router
from services.inflation import load_cpi

app = FastAPI(title="Finance PWA")
add_error_handlers(app)  # error replies carry a "code" the frontend translates (errors.py)
create_tables()
load_cpi()  # read the Statistics Mauritius CPI file once (missing file → "Inflation data unavailable")
app.include_router(auth_router)
app.include_router(summary_router)
app.include_router(income_router)
app.include_router(expenses_router)
app.include_router(budgets_router)
app.include_router(savings_router)
app.include_router(goals_router)
app.include_router(loans_router)
app.include_router(inflation_router)
app.include_router(game_router)  # Arcade: Budget Challenge
app.include_router(dashboard_router)  # Dashboard tab (plain maths, never the AI)
app.include_router(info_router)  # optional info: provided / none / missing
app.include_router(my_loans_router)  # saved loans (optional)
app.include_router(insights_router)  # Financial insights (Groq only on the button)
app.include_router(profile_router)  # Profile tab: own account details (never the password hash)


# Tell browsers to re-check frontend files every time (a quick 304 if unchanged).
# Without this a phone can keep an old api.js next to a new index.html → "getMe is not defined".
@app.middleware("http")
async def always_check_for_new_files(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

# Must come last: anything that isn't /api/... is a file from the frontend folder
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
