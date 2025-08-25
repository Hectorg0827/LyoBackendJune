"""
Google Ads/Ad Manager provider facade.
Returns ad unit configuration to clients and acts as a placeholder for
server-side event pings (impressions/clicks) if needed.

No server-side ad fetching is performed (Google SDKs are client-side).
"""
from __future__ import annotations

from typing import Dict, Optional

from lyo_app.core.enhanced_config import settings


def get_provider_config() -> Dict[str, Optional[str]]:
    """Expose configured ad units and flags for clients.

    Clients (web/mobile) should use these IDs with Google SDKs (IMA/AdMob/Ad Manager).
    """
    return {
        "enabled": bool(settings.GOOGLE_ADS_ENABLED),
        "network_code": settings.GOOGLE_ADS_NETWORK_CODE,
        "app_id_ios": settings.GOOGLE_ADS_APP_ID_IOS,
        "app_id_android": settings.GOOGLE_ADS_APP_ID_ANDROID,
        "placements": {
            "feed": settings.GOOGLE_ADS_FEED_UNIT_ID,
            "story": settings.GOOGLE_ADS_STORY_UNIT_ID,
            "post": settings.GOOGLE_ADS_POST_UNIT_ID,
            "timer": settings.GOOGLE_ADS_TIMER_UNIT_ID,
        },
    }


def validate_provider_ready() -> bool:
    if not settings.GOOGLE_ADS_ENABLED:
        return False
    # Minimal requirement: at least one ad unit configured
    placements = [
        settings.GOOGLE_ADS_FEED_UNIT_ID,
        settings.GOOGLE_ADS_STORY_UNIT_ID,
        settings.GOOGLE_ADS_POST_UNIT_ID,
        settings.GOOGLE_ADS_TIMER_UNIT_ID,
    ]
    return any(bool(p) for p in placements)


def record_event(event_type: str, payload: Dict) -> None:
    """Placeholder for server-side event logging or forwarding.

    Do not proxy clicks to Google; this is for internal analytics only.
    """
    # TODO: send to analytics pipeline or log store
    # For now, just no-op.
    return
