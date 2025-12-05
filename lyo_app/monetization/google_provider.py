"""
Google Ads/Ad Manager provider facade.
Returns ad unit configuration to clients and acts as a placeholder for
server-side event pings (impressions/clicks) if needed.

No server-side ad fetching is performed (Google SDKs are client-side).
"""
from __future__ import annotations

import os
from typing import Dict, Optional

# Try to import enhanced_config, fallback to simple config if validation fails
try:
    from lyo_app.core.enhanced_config import settings
except (ValueError, Exception):
    # If enhanced_config validation fails, use simple config
    from lyo_app.core.config import settings


def get_provider_config() -> Dict[str, Optional[str]]:
    """Expose configured ad units and flags for clients.

    Clients (web/mobile) should use these IDs with Google SDKs (IMA/AdMob/Ad Manager).
    """
    return {
        "enabled": bool(getattr(settings, 'GOOGLE_ADS_ENABLED', False)),
        "network_code": getattr(settings, 'GOOGLE_ADS_NETWORK_CODE', None),
        "app_id_ios": getattr(settings, 'GOOGLE_ADS_APP_ID_IOS', None),
        "app_id_android": getattr(settings, 'GOOGLE_ADS_APP_ID_ANDROID', None),
        "placements": {
            "feed": getattr(settings, 'GOOGLE_ADS_FEED_UNIT_ID', None),
            "story": getattr(settings, 'GOOGLE_ADS_STORY_UNIT_ID', None),
            "post": getattr(settings, 'GOOGLE_ADS_POST_UNIT_ID', None),
            "timer": getattr(settings, 'GOOGLE_ADS_TIMER_UNIT_ID', None),
        },
    }


def validate_provider_ready() -> bool:
    if not getattr(settings, 'GOOGLE_ADS_ENABLED', False):
        return False
    # Minimal requirement: at least one ad unit configured
    placements = [
        getattr(settings, 'GOOGLE_ADS_FEED_UNIT_ID', None),
        getattr(settings, 'GOOGLE_ADS_STORY_UNIT_ID', None),
        getattr(settings, 'GOOGLE_ADS_POST_UNIT_ID', None),
        getattr(settings, 'GOOGLE_ADS_TIMER_UNIT_ID', None),
    ]
    return any(bool(p) for p in placements)


def record_event(event_type: str, payload: Dict) -> None:
    """Placeholder for server-side event logging or forwarding.

    Do not proxy clicks to Google; this is for internal analytics only.
    """
    # TODO: send to analytics pipeline or log store
    # For now, just no-op.
    return
