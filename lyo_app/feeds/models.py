"""
Feeds module models for social posts, comments, and interactions.
Defines the database schema for social feed functionality.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
import uuid

from sqlalchemy import Boolean, DateTime, String, Text, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from lyo_app.core.database import Base


class PostType(str, Enum):
    """Types of social posts."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    ACHIEVEMENT = "achievement"
    COURSE_PROGRESS = "course_progress"


class FeedItemType(str, Enum):
    """Types of items in the feed."""
    POST = "post"
    RECOMMENDATION = "recommendation"
    AD = "ad"
    NOTIFICATION = "notification"


class ReactionType(str, Enum):
    """Types of reactions to posts."""
    LIKE = "like"
    LOVE = "love"
    LAUGH = "laugh"
    CELEBRATE = "celebrate"
    SUPPORT = "support"


class InteractionType(str, Enum):
    """Types of interactions a user can have with a post."""
    LIKE = "like"
    COMMENT = "comment"
    SHARE = "share"
    BOOKMARK = "bookmark"
    CAPTURE = "capture"


class Post(Base):
    """Post model for social feed content."""
    
    __tablename__ = "posts"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Post content
    content: Mapped[Optional[str]] = mapped_column(Text)
    post_type: Mapped[PostType] = mapped_column(SQLEnum(PostType), nullable=False)
    
    # Media and links
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    video_url: Mapped[Optional[str]] = mapped_column(String(500))
    link_url: Mapped[Optional[str]] = mapped_column(String(500))
    link_title: Mapped[Optional[str]] = mapped_column(String(200))
    link_description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Author
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Post metadata
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Course/lesson context (for educational posts)
    course_id: Mapped[Optional[int]] = mapped_column(ForeignKey("courses.id"))
    lesson_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lessons.id"))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    reactions: Mapped[List["PostReaction"]] = relationship(
        "PostReaction", back_populates="post", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Post(id={self.id}, author_id={self.author_id}, type='{self.post_type}')>"


class Comment(Base):
    """Comment model for post discussions."""
    
    __tablename__ = "comments"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Comment content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Relationships
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Threading support (for replies to comments)
    parent_comment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("comments.id"))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    parent_comment: Mapped[Optional["Comment"]] = relationship(
        "Comment", remote_side="Comment.id", backref="replies"
    )
    reactions: Mapped[List["CommentReaction"]] = relationship(
        "CommentReaction", back_populates="comment", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Comment(id={self.id}, post_id={self.post_id}, author_id={self.author_id})>"


class PostReaction(Base):
    """Model for user reactions to posts."""
    
    __tablename__ = "post_reactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Reaction data
    reaction_type: Mapped[ReactionType] = mapped_column(
        SQLEnum(ReactionType), nullable=False
    )
    
    # Relationships
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="reactions")
    
    def __repr__(self) -> str:
        return f"<PostReaction(post_id={self.post_id}, user_id={self.user_id}, type='{self.reaction_type}')>"


class CommentReaction(Base):
    """Model for user reactions to comments."""
    
    __tablename__ = "comment_reactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Reaction data
    reaction_type: Mapped[ReactionType] = mapped_column(
        SQLEnum(ReactionType), nullable=False
    )
    
    # Relationships
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    # Relationships
    comment: Mapped["Comment"] = relationship("Comment", back_populates="reactions")
    
    def __repr__(self) -> str:
        return f"<CommentReaction(comment_id={self.comment_id}, user_id={self.user_id}, type='{self.reaction_type}')>"


class UserFollow(Base):
    """Model for user following relationships."""
    
    __tablename__ = "user_follows"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Relationships
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    following_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<UserFollow(follower_id={self.follower_id}, following_id={self.following_id})>"


class FeedItem(Base):
    """Model for personalized feed items (denormalized for performance)."""
    
    __tablename__ = "feed_items"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # User whose feed this item belongs to
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Post in the feed
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    
    # Feed ranking score (for algorithmic ordering)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    
    def __repr__(self) -> str:
        return f"<FeedItem(user_id={self.user_id}, post_id={self.post_id}, score={self.score})>"


class UserPostInteraction(Base):
    """Model to track user interactions with posts for AI optimization."""
    
    __tablename__ = "user_post_interactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # User who interacted
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Post that was interacted with
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    
    # Interaction metrics
    viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    commented: Mapped[bool] = mapped_column(Boolean, default=False)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Time spent viewing (in seconds)
    view_duration: Mapped[Optional[float]] = mapped_column(default=0.0)
    
    # Timestamps
    first_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_interacted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    
    def __repr__(self) -> str:
        return f"<UserPostInteraction(user_id={self.user_id}, post_id={self.post_id})>"


class UserInteraction(Base):
    """Model for user interactions with posts (likes, comments, shares, etc.)."""
    
    __tablename__ = "user_interactions"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User who interacted
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Post that was interacted with
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    
    # Type of interaction
    interaction_type: Mapped[InteractionType] = mapped_column(SQLEnum(InteractionType), nullable=False)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<UserInteraction(user_id={self.user_id}, post_id={self.post_id}, type='{self.interaction_type}')>"

