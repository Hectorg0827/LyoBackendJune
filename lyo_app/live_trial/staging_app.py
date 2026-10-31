"""Isolated staging-only entrypoint for the LYO Voice Lab.

This intentionally does NOT import enhanced_main or mount the classroom,
uploads, media, user-management, or other LYO application surfaces.
The live-provider trial remains hard-disabled pending a separate approval.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from lyo_app.core.database import engine
from lyo_app.auth.dependencies import get_current_user
from .budget import initialize_schema
from .staging_auth import get_staging_trial_user
from .routes import router as live_trial_router

_PROJECT_ID = "8eb44c4c-d8df-46f2-b535-e75675823469"
_ENVIRONMENT_ID = "423b2fa5-5771-4857-9de8-3d81ff0dad39"
_SERVICE_ID = "4bcbfb07-98b6-4ace-80de-3d49a098438c"
_TRIAL_PATH = "/api/v1/gpt-live-trial"


def validate_staging_runtime() -> None:
    """Fail startup closed if this service is accidentally deployed elsewhere."""
    if os.getenv("ENVIRONMENT", "").strip().lower() != "staging":
        raise RuntimeError("Voice Lab can only start in staging")

    for variable, expected in (
        ("RAILWAY_PROJECT_ID", _PROJECT_ID),
        ("RAILWAY_ENVIRONMENT_ID", _ENVIRONMENT_ID),
        ("RAILWAY_SERVICE_ID", _SERVICE_ID),
    ):
        actual = os.getenv(variable, "").strip()
        if actual and actual != expected:
            raise RuntimeError(f"Voice Lab Railway scope mismatch: {variable}")

    railway_environment = os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
    if railway_environment and railway_environment != "staging":
        raise RuntimeError("Voice Lab cannot run in a non-staging Railway environment")

    # This repair phase is a disabled, non-billable smoke test. A later
    # reviewed code change and explicit approval are needed for paid access.
    flag = os.getenv("LYO_GPT_LIVE_TRIAL_ENABLED", "false").strip().lower()
    if flag not in {"false", "0", ""}:
        raise RuntimeError("Voice Lab paid provider access is not approved")

    # No disposable SQLite fallback: the $10 reservation ledger must persist.
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        raise RuntimeError("Voice Lab requires its own PostgreSQL DATABASE_URL")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_staging_runtime()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    # Only creates the two isolated ticket/ledger tables, not the full LYO schema.
    await initialize_schema(engine)
    yield


app = FastAPI(
    title="LYO Voice Lab — Staging Only",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(live_trial_router)
# Ticket/status dependencies must resolve via the existing LYO staging API,
# never the Voice Lab's separate ledger-only database.
app.dependency_overrides[get_current_user] = get_staging_trial_user


@app.middleware("http")
async def reject_paid_trial_while_disabled(request: Request, call_next):
    """Return deterministic disabled responses without touching user auth/DB."""
    if request.url.path == f"{_TRIAL_PATH}/ticket" and request.method == "POST":
        return JSONResponse({"detail": "Staging voice trial is disabled"}, status_code=403)
    if request.url.path == f"{_TRIAL_PATH}/status" and request.method == "GET":
        return JSONResponse({"enabled": False, "cap_usd": "10.00", "session_seconds": 60})
    return await call_next(request)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok", "service": "lyo-voice-lab", "paid_gpt_live": False}
