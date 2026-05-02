"""FastAPI entrypoint mounted by `app.yaml`."""

from __future__ import annotations

import os
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from tan.api.routers import chat, incidents, kpis, observability

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
app.include_router(observability.router)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/debug/env")
def debug_env():
    keys = [
        "CATALOG",
        "SCHEMA",
        "VOLUME",
        "LLM_ENDPOINT",
        "EMBEDDING_ENDPOINT",
        "AGENT_ENDPOINT",
        "VS_ENDPOINT",
        "RULES_INDEX",
        "INCIDENTS_INDEX",
        "SQL_WAREHOUSE_ID",
        "DATABRICKS_HOST",
        "DATABRICKS_WAREHOUSE_ID",
    ]
    return {k: os.environ.get(k) for k in keys}


@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "path": request.url.path,
            "traceback": traceback.format_exc().splitlines()[-12:],
        },
    )


# Serve the built React app from `tan/api/static/` if present (created by `npm run build`).
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
