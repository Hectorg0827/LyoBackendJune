"""
Pydantic schemas for monetization and advertisements.
Defines common ad payloads used across feeds, stories, and AI flows.
"""

from datetime import datetime
from typing import Optional, Dict

from pydantic import BaseModel, Field, ConfigDict


class AdCard(BaseModel):
    """Generic ad payload for UI rendering."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique ad identifier")
    title: str = Field(..., description="Ad title or headline")
    description: Optional[str] = Field(None, description="Short ad description")
    media_url: Optional[str] = Field(None, description="Image or video URL")
    cta_text: Optional[str] = Field(None, description="Call to action text")
    cta_url: Optional[str] = Field(None, description="Call to action URL")
    advertiser: Optional[str] = Field(None, description="Advertiser display name")
    placement: str = Field(..., description="Placement hint (feed, story, post, timer)")
    duration_seconds: Optional[int] = Field(None, ge=0, description="Ad duration in seconds (for video/animated)")
    skippable_after_seconds: Optional[int] = Field(None, ge=0, description="When user can skip the ad")
    relevance_score: float = Field(0.5, ge=0.0, le=1.0, description="Relevance score for ranking")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional rendering metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Ad payload creation time")
