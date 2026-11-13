# main.py — starts the FastAPI server: creates the database tables, connects the API routes, serves the frontend.
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from database import create_tables
from routes.auth import router as auth_router
from routes.budgets import router as budgets_router
from routes.expenses import router as expenses_router

app = FastAPI(title="Finance PWA")
create_tables()
app.include_router(auth_router)
app.include_router(expenses_router)
app.include_router(budgets_router)

# Must come last: anything that isn't /api/... is a file from the frontend folder
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
