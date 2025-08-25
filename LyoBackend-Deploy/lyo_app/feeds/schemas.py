"""
Pydantic schemas for feeds module endpoints.
Defines request/response models for posts, comments, and reactions.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from lyo_app.feeds.models import PostType, ReactionType


class PostBase(BaseModel):
    """Base post schema with common fields."""
    
    content: Optional[str] = Field(None, max_length=2000, description="Post content")
    post_type: PostType = Field(..., description="Type of post")
    image_url: Optional[str] = Field(None, description="Image URL")
    video_url: Optional[str] = Field(None, description="Video URL")
    link_url: Optional[str] = Field(None, description="Link URL")
    link_title: Optional[str] = Field(None, max_length=200, description="Link title")
    link_description: Optional[str] = Field(None, max_length=500, description="Link description")
    is_public: bool = Field(default=True, description="Whether post is public")
    course_id: Optional[int] = Field(None, description="Related course ID")
    lesson_id: Optional[int] = Field(None, description="Related lesson ID")


class PostCreate(PostBase):
    """Schema for creating a new post."""
    pass


class PostUpdate(BaseModel):
    """Schema for updating post content."""
    
    content: Optional[str] = Field(None, max_length=2000)
    is_public: Optional[bool] = None
    is_pinned: Optional[bool] = None


class PostRead(PostBase):
    """Schema for reading post data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Post ID")
    author_id: int = Field(..., description="Author user ID")
    is_pinned: bool = Field(..., description="Whether post is pinned")
    created_at: datetime = Field(..., description="Post creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Aggregated data (computed)
    comment_count: Optional[int] = Field(None, description="Number of comments")
    reaction_count: Optional[int] = Field(None, description="Number of reactions")
    user_reaction: Optional[ReactionType] = Field(None, description="Current user's reaction")


class CommentBase(BaseModel):
    """Base comment schema with common fields."""
    
    content: str = Field(..., min_length=1, max_length=1000, description="Comment content")


class CommentCreate(CommentBase):
    """Schema for creating a new comment."""
    
    post_id: int = Field(..., description="Post ID to comment on")
    parent_comment_id: Optional[int] = Field(None, description="Parent comment ID for replies")


class CommentUpdate(BaseModel):
    """Schema for updating comment content."""
    
    content: str = Field(..., min_length=1, max_length=1000)


class CommentRead(CommentBase):
    """Schema for reading comment data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Comment ID")
    post_id: int = Field(..., description="Post ID")
    author_id: int = Field(..., description="Author user ID")
    parent_comment_id: Optional[int] = Field(None, description="Parent comment ID")
    created_at: datetime = Field(..., description="Comment creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Aggregated data
    reaction_count: Optional[int] = Field(None, description="Number of reactions")
    user_reaction: Optional[ReactionType] = Field(None, description="Current user's reaction")
    replies: Optional[List["CommentRead"]] = Field(None, description="Comment replies")


class PostReactionCreate(BaseModel):
    """Schema for creating a post reaction."""
    
    post_id: int = Field(..., description="Post ID to react to")
    reaction_type: ReactionType = Field(..., description="Type of reaction")


class CommentReactionCreate(BaseModel):
    """Schema for creating a comment reaction."""
    
    comment_id: int = Field(..., description="Comment ID to react to")
    reaction_type: ReactionType = Field(..., description="Type of reaction")


class ReactionRead(BaseModel):
    """Schema for reading reaction data."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Reaction ID")
    user_id: int = Field(..., description="User ID who reacted")
    reaction_type: ReactionType = Field(..., description="Type of reaction")
    created_at: datetime = Field(..., description="Reaction timestamp")


class UserFollowCreate(BaseModel):
    """Schema for following a user."""
    
    following_id: int = Field(..., description="User ID to follow")


class UserFollowRead(BaseModel):
    """Schema for reading follow relationship."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Follow relationship ID")
    follower_id: int = Field(..., description="Follower user ID")
    following_id: int = Field(..., description="Following user ID")
    created_at: datetime = Field(..., description="Follow timestamp")


class FeedResponse(BaseModel):
    """Schema for feed responses with optional sponsored items."""
    
    posts: List[PostRead] = Field(..., description="List of posts in the feed")
    total: int = Field(..., description="Total number of posts")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")
    # Optional sponsored items interleaved by the backend; clients can render if present
    sponsored: Optional[List[dict]] = Field(None, description="Interleaved sponsored items with type and ad payload")


class PostWithDetailsRead(PostRead):
    """Extended post schema with comments and reactions."""
    
    comments: List[CommentRead] = Field(..., description="Post comments")
    reactions: List[ReactionRead] = Field(..., description="Post reactions")


class UserStatsResponse(BaseModel):
    """Schema for user social statistics."""
    
    posts_count: int = Field(..., description="Number of posts by user")
    followers_count: int = Field(..., description="Number of followers")
    following_count: int = Field(..., description="Number of users being followed")
    total_reactions_received: int = Field(..., description="Total reactions received on posts")


# Forward reference resolution
CommentRead.model_rebuild()
