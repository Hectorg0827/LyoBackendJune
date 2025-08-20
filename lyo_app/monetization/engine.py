"""
Simple ad selection engine.
Currently uses a static in-memory catalog and basic rotation.
Can be replaced with a provider integration later.
"""

from __future__ import annotations

import itertools
import random
from typing import Dict, List, Optional

from .schemas import AdCard
from .google_provider import get_provider_config


_CATALOG: Dict[str, List[AdCard]] = {
    "feed": [
        AdCard(
            id="ad_feed_1",
            title="Master Data Structures Fast",
            description="Ace interviews with our 7-day intensive course.",
            media_url=None,
            cta_text="Start Free Trial",
            cta_url="https://example.com/course/dsa",
            advertiser="Lyo Academy",
            placement="feed",
            duration_seconds=0,
            skippable_after_seconds=0,
            relevance_score=0.8,
            metadata={"style": "card"},
        ),
    ],
    "story": [
        AdCard(
            id="ad_story_1",
            title="Level Up Your Python",
            description="Interactive micro-lessons. 5 mins/day.",
            media_url="https://cdn.example.com/ads/python_story.jpg",
            cta_text="Try Now",
            cta_url="https://example.com/python-boost",
            advertiser="CodeBoost",
            placement="story",
            duration_seconds=10,
            skippable_after_seconds=5,
            relevance_score=0.7,
            metadata={"overlay": "bottom"},
        ),
    ],
    "post": [
        AdCard(
            id="ad_post_1",
            title="AI Interview Simulator",
            description="Practice real interviews with AI feedback.",
            media_url="https://cdn.example.com/ads/ai_interview.png",
            cta_text="Practice Free",
            cta_url="https://example.com/ai-interview",
            advertiser="HirePrep",
            placement="post",
            duration_seconds=0,
            skippable_after_seconds=0,
            relevance_score=0.75,
            metadata={"badge": "Sponsored"},
        ),
    ],
    "timer": [
        AdCard(
            id="ad_timer_1",
            title="While we prepare your course…",
            description="Discover curated study playlists.",
            media_url=None,
            cta_text="Explore Playlists",
            cta_url="https://example.com/playlists",
            advertiser="Lyo",
            placement="timer",
            duration_seconds=8,
            skippable_after_seconds=3,
            relevance_score=0.6,
            metadata={"layout": "inline"},
        ),
    ],
}

_iterators = {k: itertools.cycle(v) for k, v in _CATALOG.items()}


def get_ad_for_placement(placement: str) -> Optional[AdCard]:
    """Return a single ad for the given placement with basic rotation."""
    ads = _CATALOG.get(placement)
    if not ads:
        return None
    try:
        return next(_iterators[placement])
    except Exception:
        return random.choice(ads)


def interleave_ads(items: List[dict], placement: str, every: int = 5) -> List[dict]:
    """Interleave a sponsored card into a list every N items.

    Adds a simple 'type' discriminator for clients: 'post' | 'ad'.
    """
    if every <= 0:
        return items
    output: List[dict] = []
    for idx, item in enumerate(items, start=1):
        output.append(item)
        if idx % every == 0:
            ad = get_ad_for_placement(placement)
            if ad:
                ad_payload = ad.model_dump()
                # Attach Google ad unit id if configured for this placement
                try:
                    cfg = get_provider_config()
                    unit_id = (cfg.get("placements") or {}).get(placement)
                    if unit_id:
                        meta = ad_payload.get("metadata") or {}
                        meta["google_ad_unit_id"] = unit_id
                        ad_payload["metadata"] = meta
                except Exception:
                    pass
                output.append({"type": "ad", "ad": ad_payload, "position": idx})
    return output
