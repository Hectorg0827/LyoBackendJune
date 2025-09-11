"""Ads provider routes: expose Google Ads/Ad Manager configuration and accept basic events."""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lyo_app.auth.dependencies import verify_access_token
from lyo_app.auth.models import User
from lyo_app.monetization.google_provider import (
    get_provider_config,
    record_event,
    validate_provider_ready,
)

router = APIRouter(prefix="/api/v1/ads", tags=["Ads"])


class AdConfigResponse(BaseModel):
    enabled: bool
    network_code: Optional[str]
    app_id_ios: Optional[str]
    app_id_android: Optional[str]
    placements: Dict[str, Optional[str]]


@router.get("/config", response_model=AdConfigResponse)
async def get_ad_config(current_user: User = Depends(verify_access_token)):
    cfg = get_provider_config()
    if not cfg.get("enabled"):
        raise HTTPException(status_code=404, detail="Ads disabled")
    if not validate_provider_ready():
        # Expose config anyway; client can decide to hide placements with no IDs
        pass
    return cfg


class AdEvent(BaseModel):
    placement: str = Field(..., description="feed|story|post|timer")
    event_type: str = Field(..., description="impression|click|closed|skipped")
    metadata: Dict[str, Optional[str]] = Field(default_factory=dict)


@router.post("/event")
async def post_ad_event(event: AdEvent, current_user: User = Depends(verify_access_token)):
    try:
        record_event(event.event_type, event.model_dump())
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record event: {e}")
