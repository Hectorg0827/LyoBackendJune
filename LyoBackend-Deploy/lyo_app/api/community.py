"""Community API endpoints for social learning features."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db_session
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.models.enhanced import User, CommunityPost, CommunityComment
from lyo_app.core.problems import NotFoundProblem, ValidationProblem

router = APIRouter()


class PostType(str, Enum):
    """Types of community posts."""
    DISCUSSION = "discussion"
    QUESTION = "question"
    ACHIEVEMENT = "achievement"
    RESOURCE = "resource"
    ANNOUNCEMENT = "announcement"


class PostCreateRequest(BaseModel):
    """Request model for creating a community post."""
    title: str = Field(..., max_length=200, description="Post title")
    content: str = Field(..., max_length=5000, description="Post content")
    post_type: PostType = Field(PostType.DISCUSSION, description="Type of post")
    tags: Optional[List[str]] = Field(None, description="Post tags")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional post metadata")


class PostUpdateRequest(BaseModel):
    """Request model for updating a community post."""
    title: Optional[str] = Field(None, max_length=200, description="Updated post title")
    content: Optional[str] = Field(None, max_length=5000, description="Updated post content")
    tags: Optional[List[str]] = Field(None, description="Updated post tags")


class CommentCreateRequest(BaseModel):
    """Request model for creating a comment."""
    content: str = Field(..., max_length=2000, description="Comment content")
    parent_comment_id: Optional[str] = Field(None, description="ID of parent comment for replies")


class CommentResponse(BaseModel):
    """Response model for comments."""
    id: str
    content: str
    author: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    likes_count: int
    replies_count: int
    parent_comment_id: Optional[str]


class PostResponse(BaseModel):
    """Response model for community posts."""
    id: str
    title: str
    content: str
    post_type: str
    author: Dict[str, Any]
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    likes_count: int
    comments_count: int
    views_count: int
    is_pinned: bool
    metadata: Dict[str, Any]


@router.get("/posts", response_model=List[PostResponse], summary="Get community posts")
async def get_community_posts(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    post_type: Optional[PostType] = Query(None, description="Filter by post type"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> List[PostResponse]:
    """Get community posts with optional filtering."""
    
    # Build query
    query = select(CommunityPost).where(CommunityPost.is_published == True)
    
    if post_type:
        query = query.where(CommunityPost.post_type == post_type.value)
    
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",")]
        # In PostgreSQL, you would use array operations for tag filtering
        # This is a simplified version
        for tag in tag_list:
            query = query.where(CommunityPost.tags.contains([tag]))
    
    # Order by pinned posts first, then by creation date
    query = query.order_by(desc(CommunityPost.is_pinned), desc(CommunityPost.created_at))
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    posts = result.scalars().all()
    
    # Convert to response format
    post_responses = []
    for post in posts:
        # Get author info
        author_query = await db.execute(
            select(User).where(User.id == post.author_id)
        )
        author = author_query.scalar_one_or_none()
        
        # Get comment count
        comment_count_query = await db.execute(
            select(func.count(CommunityComment.id)).where(CommunityComment.post_id == post.id)
        )
        comments_count = comment_count_query.scalar() or 0
        
        post_responses.append(PostResponse(
            id=str(post.id),
            title=post.title,
            content=post.content,
            post_type=post.post_type,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            tags=post.tags or [],
            created_at=post.created_at,
            updated_at=post.updated_at,
            likes_count=post.likes_count,
            comments_count=comments_count,
            views_count=post.views_count,
            is_pinned=post.is_pinned,
            metadata=post.metadata or {}
        ))
    
    return post_responses


@router.post("/posts", response_model=PostResponse, summary="Create community post")
async def create_community_post(
    post_data: PostCreateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> PostResponse:
    """Create a new community post."""
    
    # Create the post
    post = CommunityPost(
        title=post_data.title,
        content=post_data.content,
        post_type=post_data.post_type.value,
        author_id=current_user.id,
        tags=post_data.tags or [],
        metadata=post_data.metadata or {},
        is_published=True
    )
    
    db.add(post)
    await db.commit()
    await db.refresh(post)
    
    return PostResponse(
        id=str(post.id),
        title=post.title,
        content=post.content,
        post_type=post.post_type,
        author={
            "id": str(current_user.id),
            "name": current_user.full_name,
            "avatar_url": current_user.profile_data.get("avatar_url") if current_user.profile_data else None
        },
        tags=post.tags or [],
        created_at=post.created_at,
        updated_at=post.updated_at,
        likes_count=0,
        comments_count=0,
        views_count=0,
        is_pinned=False,
        metadata=post.metadata or {}
    )


@router.get("/posts/{post_id}", response_model=PostResponse, summary="Get community post")
async def get_community_post(
    post_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> PostResponse:
    """Get a specific community post and increment view count."""
    
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    # Increment view count
    post.views_count += 1
    await db.commit()
    
    # Get author info
    author_query = await db.execute(
        select(User).where(User.id == post.author_id)
    )
    author = author_query.scalar_one_or_none()
    
    # Get comment count
    comment_count_query = await db.execute(
        select(func.count(CommunityComment.id)).where(CommunityComment.post_id == post.id)
    )
    comments_count = comment_count_query.scalar() or 0
    
    return PostResponse(
        id=str(post.id),
        title=post.title,
        content=post.content,
        post_type=post.post_type,
        author={
            "id": str(author.id) if author else "unknown",
            "name": author.full_name if author else "Unknown User",
            "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
        },
        tags=post.tags or [],
        created_at=post.created_at,
        updated_at=post.updated_at,
        likes_count=post.likes_count,
        comments_count=comments_count,
        views_count=post.views_count,
        is_pinned=post.is_pinned,
        metadata=post.metadata or {}
    )


@router.put("/posts/{post_id}", response_model=PostResponse, summary="Update community post")
async def update_community_post(
    post_id: str,
    post_update: PostUpdateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> PostResponse:
    """Update a community post (only by the author)."""
    
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    if post.author_id != current_user.id:
        raise ValidationProblem("You can only update your own posts")
    
    # Update fields if provided
    if post_update.title is not None:
        post.title = post_update.title
    if post_update.content is not None:
        post.content = post_update.content
    if post_update.tags is not None:
        post.tags = post_update.tags
    
    await db.commit()
    await db.refresh(post)
    
    # Get comment count
    comment_count_query = await db.execute(
        select(func.count(CommunityComment.id)).where(CommunityComment.post_id == post.id)
    )
    comments_count = comment_count_query.scalar() or 0
    
    return PostResponse(
        id=str(post.id),
        title=post.title,
        content=post.content,
        post_type=post.post_type,
        author={
            "id": str(current_user.id),
            "name": current_user.full_name,
            "avatar_url": current_user.profile_data.get("avatar_url") if current_user.profile_data else None
        },
        tags=post.tags or [],
        created_at=post.created_at,
        updated_at=post.updated_at,
        likes_count=post.likes_count,
        comments_count=comments_count,
        views_count=post.views_count,
        is_pinned=post.is_pinned,
        metadata=post.metadata or {}
    )


@router.delete("/posts/{post_id}", summary="Delete community post")
async def delete_community_post(
    post_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete a community post (only by the author)."""
    
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    if post.author_id != current_user.id:
        raise ValidationProblem("You can only delete your own posts")
    
    await db.delete(post)
    await db.commit()
    
    return {"message": "Post deleted successfully"}


@router.post("/posts/{post_id}/like", summary="Like/unlike a post")
async def toggle_post_like(
    post_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Toggle like status for a community post."""
    
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    # In production, this would use a separate likes table
    # For now, just increment/decrement the count
    # This is a simplified implementation
    
    if not post.metadata:
        post.metadata = {}
    
    user_likes = post.metadata.get("user_likes", [])
    user_id_str = str(current_user.id)
    
    if user_id_str in user_likes:
        # Unlike
        user_likes.remove(user_id_str)
        post.likes_count = max(0, post.likes_count - 1)
        action = "unliked"
    else:
        # Like
        user_likes.append(user_id_str)
        post.likes_count += 1
        action = "liked"
    
    post.metadata["user_likes"] = user_likes
    await db.commit()
    
    return {
        "message": f"Post {action} successfully",
        "likes_count": post.likes_count,
        "user_liked": action == "liked"
    }


# Comment endpoints

@router.get("/posts/{post_id}/comments", response_model=List[CommentResponse], summary="Get post comments")
async def get_post_comments(
    post_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
) -> List[CommentResponse]:
    """Get comments for a specific post."""
    
    # Verify post exists
    post_result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    # Get comments
    result = await db.execute(
        select(CommunityComment).where(CommunityComment.post_id == post_id)
        .order_by(CommunityComment.created_at)
        .offset(offset).limit(limit)
    )
    comments = result.scalars().all()
    
    # Convert to response format
    comment_responses = []
    for comment in comments:
        # Get author info
        author_query = await db.execute(
            select(User).where(User.id == comment.author_id)
        )
        author = author_query.scalar_one_or_none()
        
        # Get reply count for this comment
        reply_count_query = await db.execute(
            select(func.count(CommunityComment.id)).where(
                CommunityComment.parent_comment_id == comment.id
            )
        )
        replies_count = reply_count_query.scalar() or 0
        
        comment_responses.append(CommentResponse(
            id=str(comment.id),
            content=comment.content,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            likes_count=comment.likes_count,
            replies_count=replies_count,
            parent_comment_id=str(comment.parent_comment_id) if comment.parent_comment_id else None
        ))
    
    return comment_responses


@router.post("/posts/{post_id}/comments", response_model=CommentResponse, summary="Create comment")
async def create_comment(
    post_id: str,
    comment_data: CommentCreateRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> CommentResponse:
    """Create a new comment on a post."""
    
    # Verify post exists
    post_result = await db.execute(
        select(CommunityPost).where(CommunityPost.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    
    if not post:
        raise NotFoundProblem("Post not found")
    
    # Verify parent comment exists if specified
    if comment_data.parent_comment_id:
        parent_result = await db.execute(
            select(CommunityComment).where(
                CommunityComment.id == comment_data.parent_comment_id,
                CommunityComment.post_id == post_id
            )
        )
        parent_comment = parent_result.scalar_one_or_none()
        
        if not parent_comment:
            raise NotFoundProblem("Parent comment not found")
    
    # Create comment
    comment = CommunityComment(
        content=comment_data.content,
        post_id=post.id,
        author_id=current_user.id,
        parent_comment_id=comment_data.parent_comment_id
    )
    
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    
    return CommentResponse(
        id=str(comment.id),
        content=comment.content,
        author={
            "id": str(current_user.id),
            "name": current_user.full_name,
            "avatar_url": current_user.profile_data.get("avatar_url") if current_user.profile_data else None
        },
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        likes_count=0,
        replies_count=0,
        parent_comment_id=str(comment.parent_comment_id) if comment.parent_comment_id else None
    )


@router.delete("/comments/{comment_id}", summary="Delete comment")
async def delete_comment(
    comment_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete a comment (only by the author)."""
    
    result = await db.execute(
        select(CommunityComment).where(CommunityComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise NotFoundProblem("Comment not found")
    
    if comment.author_id != current_user.id:
        raise ValidationProblem("You can only delete your own comments")
    
    await db.delete(comment)
    await db.commit()
    
    return {"message": "Comment deleted successfully"}
