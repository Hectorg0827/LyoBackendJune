"""
Feeds routes for social interactions, posts, comments, and reactions.
Provides FastAPI endpoints for the feeds module.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.auth.routes import get_current_user
from lyo_app.auth.schemas import UserRead
from lyo_app.core.database import get_db
from lyo_app.core.database import get_db
from lyo_app.feeds.schemas import (
    PostCreate, PostUpdate, PostRead, PostWithDetailsRead,
    CommentCreate, CommentUpdate, CommentRead,
    PostReactionCreate, CommentReactionCreate, ReactionRead,
    UserFollowCreate, UserFollowRead,
    FeedResponse, UserStatsResponse
)
from lyo_app.feeds.service import FeedsService
from lyo_app.stack.schemas import StackItemRead

router = APIRouter()
feeds_service = FeedsService()


# Post endpoints
@router.post("/posts", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PostRead:
    """
    Create a new post.
    
    Args:
        post_data: Post creation data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created post data
    """
    try:
        post = await feeds_service.create_post(db, current_user.id, post_data)
        return PostRead.model_validate(post)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/posts/{post_id}", response_model=PostWithDetailsRead)
async def get_post(
    post_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PostWithDetailsRead:
    """
    Get a post with comments and reactions.
    
    Args:
        post_id: Post ID to retrieve
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Post data with comments and reactions
        
    Raises:
        HTTPException: If post not found
    """
    post = await feeds_service.get_post_with_details(db, post_id, current_user.id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    return post


@router.put("/posts/{post_id}", response_model=PostRead)
async def update_post(
    post_id: int,
    post_data: PostUpdate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PostRead:
    """
    Update a post.
    
    Args:
        post_id: Post ID to update
        post_data: Post update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated post data
        
    Raises:
        HTTPException: If post not found or user not authorized
    """
    try:
        post = await feeds_service.update_post(db, post_id, current_user.id, post_data)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        return PostRead.model_validate(post)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Delete a post.
    
    Args:
        post_id: Post ID to delete
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If post not found or user not authorized
    """
    try:
        success = await feeds_service.delete_post(db, post_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post"
        )


# Comment endpoints
@router.post("/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: CommentCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CommentRead:
    """
    Create a new comment.
    
    Args:
        comment_data: Comment creation data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created comment data
    """
    try:
        comment = await feeds_service.create_comment(db, current_user.id, comment_data)
        return CommentRead.model_validate(comment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/comments/{comment_id}", response_model=CommentRead)
async def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CommentRead:
    """
    Update a comment.
    
    Args:
        comment_id: Comment ID to update
        comment_data: Comment update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated comment data
        
    Raises:
        HTTPException: If comment not found or user not authorized
    """
    try:
        comment = await feeds_service.update_comment(db, comment_id, current_user.id, comment_data)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        return CommentRead.model_validate(comment)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Delete a comment.
    
    Args:
        comment_id: Comment ID to delete
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If comment not found or user not authorized
    """
    try:
        success = await feeds_service.delete_comment(db, comment_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )


# Reaction endpoints
@router.post("/posts/{post_id}/reactions", response_model=ReactionRead, status_code=status.HTTP_201_CREATED)
async def react_to_post(
    post_id: int,
    reaction_data: PostReactionCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> ReactionRead:
    """
    React to a post.
    
    Args:
        post_id: Post ID to react to
        reaction_data: Reaction data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created reaction data
    """
    # Ensure post_id matches the URL parameter
    if reaction_data.post_id != post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post ID in URL and body must match"
        )
    
    try:
        reaction = await feeds_service.react_to_post(db, current_user.id, reaction_data)
        return ReactionRead.model_validate(reaction)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/posts/{post_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_post_reaction(
    post_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Remove reaction from a post.
    
    Args:
        post_id: Post ID to remove reaction from
        current_user: Current authenticated user
        db: Database session
    """
    await feeds_service.remove_post_reaction(db, current_user.id, post_id)


@router.post("/comments/{comment_id}/reactions", response_model=ReactionRead, status_code=status.HTTP_201_CREATED)
async def react_to_comment(
    comment_id: int,
    reaction_data: CommentReactionCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> ReactionRead:
    """
    React to a comment.
    
    Args:
        comment_id: Comment ID to react to
        reaction_data: Reaction data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created reaction data
    """
    # Ensure comment_id matches the URL parameter
    if reaction_data.comment_id != comment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comment ID in URL and body must match"
        )
    
    try:
        reaction = await feeds_service.react_to_comment(db, current_user.id, reaction_data)
        return ReactionRead.model_validate(reaction)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/comments/{comment_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_comment_reaction(
    comment_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Remove reaction from a comment.
    
    Args:
        comment_id: Comment ID to remove reaction from
        current_user: Current authenticated user
        db: Database session
    """
    await feeds_service.remove_comment_reaction(db, current_user.id, comment_id)


# Follow endpoints
@router.post("/follow", response_model=UserFollowRead, status_code=status.HTTP_201_CREATED)
async def follow_user(
    follow_data: UserFollowCreate,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserFollowRead:
    """
    Follow a user.
    
    Args:
        follow_data: Follow data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created follow relationship data
    """
    try:
        follow = await feeds_service.follow_user(db, current_user.id, follow_data)
        return UserFollowRead.model_validate(follow)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/follow/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    user_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Unfollow a user.
    
    Args:
        user_id: User ID to unfollow
        current_user: Current authenticated user
        db: Database session
    """
    await feeds_service.unfollow_user(db, current_user.id, user_id)


# Feed endpoints
@router.get("/feed", response_model=FeedResponse)
async def get_user_feed(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
) -> FeedResponse:
    """
    Get personalized feed for the current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        page: Page number (1-based)
        per_page: Number of items per page
        
    Returns:
        Paginated feed response
    """
    return await feeds_service.get_user_feed(db, current_user.id, page, per_page)


@router.get("/feed/public", response_model=FeedResponse)
async def get_public_feed(
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    lesson_id: Optional[int] = Query(None, description="Filter by lesson ID")
) -> FeedResponse:
    """
    Get public feed.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        page: Page number (1-based)
        per_page: Number of items per page
        course_id: Optional course context
        lesson_id: Optional lesson context
        
    Returns:
        Paginated public feed response
    """
    return await feeds_service.get_public_feed(
        db, 
        current_user.id, 
        page, 
        per_page,
        course_id=course_id,
        lesson_id=lesson_id
    )


@router.post("/posts/{post_id}/capture", response_model=StackItemRead)
async def capture_post(
    post_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> StackItemRead:
    """
    Capture a post to the user's stack.
    
    Args:
        post_id: Post ID to capture
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created StackItem
    """
    try:
        stack_item = await feeds_service.capture_post(db, current_user.id, post_id)
        return StackItemRead.model_validate(stack_item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to capture post: {str(e)}"
        )


@router.get("/users/{user_id}/posts", response_model=FeedResponse)
async def get_user_posts(
    user_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
) -> FeedResponse:
    """
    Get posts by a specific user.
    
    Args:
        user_id: User ID whose posts to retrieve
        current_user: Current authenticated user
        db: Database session
        page: Page number (1-based)
        per_page: Number of items per page
        
    Returns:
        Paginated user posts response
    """
    return await feeds_service.get_user_posts(db, user_id, current_user.id, page, per_page)


@router.get("/users/{user_id}/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_id: int,
    current_user: Annotated[UserRead, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserStatsResponse:
    """
    Get social statistics for a user.
    
    Args:
        user_id: User ID to get stats for
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        User social statistics
    """
    return await feeds_service.get_user_stats(db, user_id)
