# main.py — starts the FastAPI server: creates the database tables, connects the API routes, serves the frontend.
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from database import create_tables
from routes.auth import router as auth_router

app = FastAPI(title="Finance PWA")
create_tables()
app.include_router(auth_router)

# Must come last: anything that isn't /api/... is a file from the frontend folder
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
