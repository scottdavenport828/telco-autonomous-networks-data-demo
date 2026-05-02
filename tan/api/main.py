"""FastAPI entrypoint mounted by `app.yaml`."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tan.api.routers import chat, incidents, kpis

app = FastAPI(
    title="Telco Autonomous Networks — Databricks-native demo",
    version="0.1.0",
)

# Allow the React dev server to talk to the API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(kpis.router)
app.include_router(incidents.router)
app.include_router(chat.router)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}


# Serve the built React app from `tan/api/static/` if present (created by `npm run build`).
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
