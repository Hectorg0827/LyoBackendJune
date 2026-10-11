"""Isolated, token-protected media validation service; never a production entrypoint.

Runs the production upload/stream router against the release bucket without
creating learner accounts or feed records. Its Railway config skips migrations.
"""
import hmac
import os
import uuid
from types import SimpleNamespace

from fastapi import Depends, FastAPI, Header, HTTPException

from lyo_app.core.config import settings
from lyo_app.routers import user_media

if not settings.testing or os.getenv("DISCOVER_VALIDATION_ENABLED") != "true":
    raise RuntimeError("The Discover validation server requires explicit test configuration")

TOKEN = os.environ["DISCOVER_VALIDATION_TOKEN"]
if len(TOKEN) < 32:
    raise RuntimeError("Use a strong validation token")
BOOT_ID = uuid.uuid4().hex
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def validation_user(authorization: str = Header(default="")):
    if not hmac.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(status_code=401, detail="Validation token required")
    return SimpleNamespace(id=0)


app.dependency_overrides[user_media.get_current_user] = validation_user
app.include_router(user_media.router)


@app.middleware("http")
async def identify_replica(request, call_next):
    response = await call_next(request)
    response.headers["X-Validation-Boot-ID"] = BOOT_ID
    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "validation": True, "boot_id": BOOT_ID}


@app.get("/validation/state", dependencies=[Depends(validation_user)])
async def validation_state():
    return {
        "boot_id": BOOT_ID,
        "local_media_files": sum(1 for p in user_media._media_root().rglob("*") if p.is_file()),
        "commit": os.getenv("RAILWAY_GIT_COMMIT_SHA"),
    }
