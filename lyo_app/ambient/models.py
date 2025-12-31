"""
Database models for Ambient Presence System
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from lyo_app.core.database import Base
from lyo_app.tenants.mixins import TenantMixin


class AmbientPresenceState(TenantMixin, Base):
    """
    Tracks user's current presence state for ambient assistance.
    Updated in real-time as user navigates the app.
    """

    __tablename__ = "ambient_presence_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Current state
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Current context
    current_page: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    current_content_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    time_on_page: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # seconds

    # Behavior tracking
    scroll_count: Mapped[int] = mapped_column(Integer, default=0)
    mouse_hesitations: Mapped[int] = mapped_column(Integer, default=0)

    # Daily limits (prevent over-notification)
    inline_help_count_today: Mapped[int] = mapped_column(Integer, default=0)
    quick_access_count_today: Mapped[int] = mapped_column(Integer, default=0)

    # Full context (JSONB for flexibility)
    context: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class QuickActionType(str, Enum):
    """Types of quick actions available"""
    ASK_ANYTHING = "ask_anything"
    EXPLAIN_CONCEPT = "explain_concept"
    PRACTICE_QUESTIONS = "practice_questions"
    HINT = "hint"
    SIMILAR_EXAMPLE = "similar_example"
    REVIEW_STRUGGLE = "review_struggle"
    SUMMARIZE = "summarize"
    CREATE_NOTE = "create_note"


class QuickAction:
    """
    Quick action item for Cmd+K palette or floating widget.
    Not a database model - generated on-the-fly based on context.
    """

    def __init__(
        self,
        id: str,
        label: str,
        action_type: QuickActionType,
        icon: str = "💬",
        context: Optional[Dict[str, Any]] = None
    ):
        self.id = id
        self.label = label
        self.action_type = action_type
        self.icon = icon
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "action_type": self.action_type,
            "icon": self.icon,
            "context": self.context
        }


class InlineHelpLog(TenantMixin, Base):
    """
    Logs when inline help is shown and user's response.
    Used for learning what works and respecting user preferences.
    """

    __tablename__ = "inline_help_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # What help was offered
    help_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'explain', 'hint', 'stuck'
    help_text: Mapped[str] = mapped_column(String(500), nullable=False)

    # Context
    page: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # User response
    user_response: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # 'accepted', 'dismissed', 'ignored'
    response_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    shown_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
