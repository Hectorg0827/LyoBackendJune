"""Feeds API endpoints for content discovery and social learning with AI ranking."""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db_session
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.models.enhanced import User, ContentItem
from lyo_app.core.problems import ResourceNotFoundProblem, ValidationProblem
from lyo_app.api.feed_ranking import feed_ranking_service, RankingStrategy

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedType(str, Enum):
    """Types of content feeds."""
    RECOMMENDED = "recommended"
    TRENDING = "trending"
    FOLLOWING = "following"
    RECENT = "recent"
    PERSONALIZED = "personalized"
    AI_RANKED = "ai_ranked"


class ContentType(str, Enum):
    """Types of content items."""
    COURSE = "course"
    LESSON = "lesson"
    ARTICLE = "article"
    VIDEO = "video"
    QUIZ = "quiz"


class FeedItemResponse(BaseModel):
    """Response model for feed items."""
    id: str
    content_type: str
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    author: Dict[str, Any]
    engagement_stats: Dict[str, int]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    ranking_score: Optional[float] = None
    ranking_signals: Optional[Dict[str, float]] = None


class FeedResponse(BaseModel):
    """Response model for feed data."""
    feed_type: str
    items: List[FeedItemResponse]
    total_count: int
    next_cursor: Optional[str]
    refresh_timestamp: datetime


@router.get("/", response_model=FeedResponse, summary="Get personalized feed")
async def get_main_feed(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    feed_type: FeedType = Query(FeedType.PERSONALIZED, description="Type of feed to retrieve"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to retrieve"),
    cursor: Optional[str] = Query(None, description="Pagination cursor")
) -> FeedResponse:
    """
    Get the main content feed for the user.
    
    Feed types:
    - **personalized**: AI-curated content based on user preferences and history
    - **recommended**: General recommendations for the user's skill level
    - **trending**: Popular content across the platform
    - **following**: Content from users the current user follows
    - **recent**: Recently published content
    """
    # Base query for content items
    query = select(ContentItem).where(ContentItem.is_published == True)
    
    if feed_type == FeedType.TRENDING:
        # Sort by engagement metrics (placeholder logic)
        query = query.order_by(desc(ContentItem.created_at))
    elif feed_type == FeedType.RECENT:
        query = query.order_by(desc(ContentItem.created_at))
    elif feed_type == FeedType.PERSONALIZED:
        # In production, this would use ML/AI for personalization
        query = query.order_by(desc(ContentItem.updated_at))
    else:
        # Default ordering
        query = query.order_by(desc(ContentItem.created_at))
    
    # Apply pagination
    query = query.limit(limit)
    
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    # Convert to feed items
    feed_items = []
    for item in content_items:
        # Get author information (would be joined in production)
        author_query = await db.execute(
            select(User).where(User.id == item.created_by)
        )
        author = author_query.scalar_one_or_none()
        
        feed_items.append(FeedItemResponse(
            id=str(item.id),
            content_type=item.content_type,
            title=item.title,
            description=item.description,
            thumbnail_url=item.metadata.get("thumbnail_url") if item.metadata else None,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            engagement_stats={
                "views": item.metadata.get("views", 0) if item.metadata else 0,
                "likes": item.metadata.get("likes", 0) if item.metadata else 0,
                "comments": item.metadata.get("comments", 0) if item.metadata else 0
            },
            created_at=item.created_at,
            updated_at=item.updated_at,
            metadata=item.metadata or {}
        ))
    
    return FeedResponse(
        feed_type=feed_type.value,
        items=feed_items,
        total_count=len(feed_items),
        next_cursor=None,  # Would implement proper pagination in production
        refresh_timestamp=datetime.utcnow()
    )


@router.get("/trending", response_model=List[FeedItemResponse], summary="Get trending content")
async def get_trending_content(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    content_type: Optional[ContentType] = Query(None, description="Filter by content type"),
    timeframe: int = Query(7, description="Trending timeframe in days")
) -> List[FeedItemResponse]:
    """Get trending content based on engagement metrics."""
    
    # Calculate date threshold
    date_threshold = datetime.utcnow() - timedelta(days=timeframe)
    
    # Base query
    query = select(ContentItem).where(
        and_(
            ContentItem.is_published == True,
            ContentItem.created_at >= date_threshold
        )
    )
    
    # Filter by content type if specified
    if content_type:
        query = query.where(ContentItem.content_type == content_type.value)
    
    # Order by engagement (placeholder - would use actual metrics in production)
    query = query.order_by(desc(ContentItem.created_at)).limit(50)
    
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    # Convert to response format
    trending_items = []
    for item in content_items:
        author_query = await db.execute(
            select(User).where(User.id == item.created_by)
        )
        author = author_query.scalar_one_or_none()
        
        trending_items.append(FeedItemResponse(
            id=str(item.id),
            content_type=item.content_type,
            title=item.title,
            description=item.description,
            thumbnail_url=item.metadata.get("thumbnail_url") if item.metadata else None,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            engagement_stats={
                "views": item.metadata.get("views", 0) if item.metadata else 0,
                "likes": item.metadata.get("likes", 0) if item.metadata else 0,
                "comments": item.metadata.get("comments", 0) if item.metadata else 0
            },
            created_at=item.created_at,
            updated_at=item.updated_at,
            metadata=item.metadata or {}
        ))
    
    return trending_items


@router.get("/recommendations", response_model=List[FeedItemResponse], summary="Get personalized recommendations")
async def get_recommendations(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(10, ge=1, le=50)
) -> List[FeedItemResponse]:
    """
    Get AI-powered personalized content recommendations.
    
    This endpoint would integrate with the content curator service
    to provide intelligent recommendations based on:
    - User's learning history and preferences
    - Current skill level and progress
    - Similar users' activities
    - Content performance metrics
    """
    
    # Placeholder implementation - in production this would use ML/AI
    # For now, get recent content items
    query = select(ContentItem).where(
        ContentItem.is_published == True
    ).order_by(desc(ContentItem.updated_at)).limit(limit)
    
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    recommendations = []
    for item in content_items:
        author_query = await db.execute(
            select(User).where(User.id == item.created_by)
        )
        author = author_query.scalar_one_or_none()
        
        recommendations.append(FeedItemResponse(
            id=str(item.id),
            content_type=item.content_type,
            title=item.title,
            description=item.description,
            thumbnail_url=item.metadata.get("thumbnail_url") if item.metadata else None,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            engagement_stats={
                "views": item.metadata.get("views", 0) if item.metadata else 0,
                "likes": item.metadata.get("likes", 0) if item.metadata else 0,
                "comments": item.metadata.get("comments", 0) if item.metadata else 0
            },
            created_at=item.created_at,
            updated_at=item.updated_at,
            metadata=item.metadata or {}
        ))
    
    return recommendations


class FeedInteractionRequest(BaseModel):
    """Request model for feed interactions."""
    action: str = Field(..., description="Action type: like, unlike, bookmark, share, etc.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional interaction data")


@router.post("/items/{item_id}/interact", summary="Interact with feed item")
async def interact_with_item(
    item_id: str,
    interaction: FeedInteractionRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Interact with a feed item (like, bookmark, share, etc.).
    
    Supported actions:
    - **like**: Like the content item
    - **unlike**: Remove like from the content item
    - **bookmark**: Bookmark for later viewing
    - **unbookmark**: Remove bookmark
    - **share**: Share the content item
    - **view**: Track that the user viewed the content
    """
    
    # Check if content item exists
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == item_id)
    )
    content_item = result.scalar_one_or_none()
    
    if not content_item:
        raise ResourceNotFoundProblem("Content item not found")
    
    # Process the interaction
    if interaction.action in ["like", "unlike", "bookmark", "unbookmark", "share", "view"]:
        # In production, this would update interaction tables and metrics
        # For now, just update metadata
        
        if not content_item.metadata:
            content_item.metadata = {}
        
        if interaction.action == "like":
            current_likes = content_item.metadata.get("likes", 0)
            content_item.metadata["likes"] = current_likes + 1
        elif interaction.action == "unlike":
            current_likes = content_item.metadata.get("likes", 0)
            content_item.metadata["likes"] = max(0, current_likes - 1)
        elif interaction.action == "view":
            current_views = content_item.metadata.get("views", 0)
            content_item.metadata["views"] = current_views + 1
        elif interaction.action == "share":
            current_shares = content_item.metadata.get("shares", 0)
            content_item.metadata["shares"] = current_shares + 1
        
        await db.commit()
        
        # Add background task for analytics/recommendations update
        background_tasks.add_task(
            _update_interaction_analytics,
            str(current_user.id),
            item_id,
            interaction.action,
            interaction.metadata or {}
        )
        
        return {
            "message": f"Interaction '{interaction.action}' recorded successfully",
            "item_id": item_id,
            "action": interaction.action
        }
    else:
        raise ValidationProblem(f"Unsupported action: {interaction.action}")


async def _update_interaction_analytics(
    user_id: str,
    item_id: str,
    action: str,
    metadata: Dict[str, Any]
):
    """Background task to update interaction analytics."""
    # In production, this would:
    # - Update user interaction history
    # - Update content engagement metrics
    # - Feed data to recommendation engine
    # - Update trending calculations
    
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Processing interaction: user={user_id}, item={item_id}, action={action}")
    
    # Placeholder for analytics processing
    pass


@router.get("/search", response_model=List[FeedItemResponse], summary="Search content")
async def search_content(
    q: str = Query(..., description="Search query"),
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    content_type: Optional[ContentType] = Query(None, description="Filter by content type"),
    limit: int = Query(20, ge=1, le=100)
) -> List[FeedItemResponse]:
    """
    Search for content items.
    
    In production, this would use full-text search capabilities
    like PostgreSQL's full-text search or Elasticsearch.
    """
    
    # Simple search implementation (would use proper search in production)
    query = select(ContentItem).where(
        and_(
            ContentItem.is_published == True,
            or_(
                ContentItem.title.ilike(f"%{q}%"),
                ContentItem.description.ilike(f"%{q}%")
            )
        )
    )
    
    if content_type:
        query = query.where(ContentItem.content_type == content_type.value)
    
    query = query.order_by(desc(ContentItem.created_at)).limit(limit)
    
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    search_results = []
    for item in content_items:
        author_query = await db.execute(
            select(User).where(User.id == item.created_by)
        )
        author = author_query.scalar_one_or_none()
        
        search_results.append(FeedItemResponse(
            id=str(item.id),
            content_type=item.content_type,
            title=item.title,
            description=item.description,
            thumbnail_url=item.metadata.get("thumbnail_url") if item.metadata else None,
            author={
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            engagement_stats={
                "views": item.metadata.get("views", 0) if item.metadata else 0,
                "likes": item.metadata.get("likes", 0) if item.metadata else 0,
                "comments": item.metadata.get("comments", 0) if item.metadata else 0
            },
            created_at=item.created_at,
            updated_at=item.updated_at,
            metadata=item.metadata or {}
        ))
    
    return search_results


# ============================================================================
# AI RANKING ENDPOINTS
# ============================================================================

class RankingPreferencesRequest(BaseModel):
    """User preferences for feed ranking."""
    interests: List[str] = Field(default_factory=list, description="User interests/topics")
    learning_goals: List[str] = Field(default_factory=list, description="Learning goals")
    preferred_content_types: List[str] = Field(default_factory=list, description="Preferred content types")
    engagement_weight: float = Field(0.25, ge=0, le=1, description="Weight for engagement signals")
    freshness_weight: float = Field(0.15, ge=0, le=1, description="Weight for content freshness")


@router.get("/ai-ranked", response_model=FeedResponse, summary="Get AI-ranked feed")
async def get_ai_ranked_feed(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    strategy: str = Query("personalized", description="Ranking strategy: personalized, trending, engagement, chronological"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to retrieve"),
    cursor: Optional[str] = Query(None, description="Pagination cursor")
) -> FeedResponse:
    """
    Get AI-ranked content feed.
    
    Uses machine learning signals to rank content based on:
    - User engagement history and preferences
    - Content quality signals (completion rate, ratings)
    - Social signals (follows, similar users)
    - Freshness and trending velocity
    
    **Strategies:**
    - `personalized`: Best overall recommendation based on all signals
    - `trending`: Content gaining engagement rapidly  
    - `engagement`: Highest engagement content
    - `chronological`: Simple time-based ordering
    """
    # Map string to enum
    strategy_map = {
        "personalized": RankingStrategy.PERSONALIZED,
        "trending": RankingStrategy.TRENDING,
        "engagement": RankingStrategy.ENGAGEMENT,
        "chronological": RankingStrategy.CHRONOLOGICAL,
        "learning_goal": RankingStrategy.LEARNING_GOAL
    }
    ranking_strategy = strategy_map.get(strategy, RankingStrategy.PERSONALIZED)
    
    # Get content items
    query = select(ContentItem).where(ContentItem.is_published == True)
    query = query.order_by(desc(ContentItem.created_at)).limit(limit * 2)  # Fetch more for ranking
    
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    # Convert to dict format for ranking
    items_for_ranking = []
    for item in content_items:
        author_query = await db.execute(
            select(User).where(User.id == item.created_by)
        )
        author = author_query.scalar_one_or_none()
        
        items_for_ranking.append({
            "id": str(item.id),
            "content_type": item.content_type,
            "title": item.title,
            "description": item.description,
            "thumbnail_url": item.metadata.get("thumbnail_url") if item.metadata else None,
            "author": {
                "id": str(author.id) if author else "unknown",
                "name": author.full_name if author else "Unknown User",
                "avatar_url": author.profile_data.get("avatar_url") if author and author.profile_data else None
            },
            "engagement_stats": {
                "views": item.metadata.get("views", 0) if item.metadata else 0,
                "likes": item.metadata.get("likes", 0) if item.metadata else 0,
                "comments": item.metadata.get("comments", 0) if item.metadata else 0
            },
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "metadata": item.metadata or {},
            "tags": item.metadata.get("tags", []) if item.metadata else []
        })
    
    # Apply AI ranking
    ranked_items = await feed_ranking_service.rank_feed(
        db=db,
        user_id=str(current_user.id),
        content_items=items_for_ranking,
        strategy=ranking_strategy
    )
    
    # Convert to response and limit
    feed_items = [
        FeedItemResponse(
            id=item["id"],
            content_type=item["content_type"],
            title=item["title"],
            description=item.get("description"),
            thumbnail_url=item.get("thumbnail_url"),
            author=item["author"],
            engagement_stats=item["engagement_stats"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            metadata=item.get("metadata", {}),
            ranking_score=item.get("ranking_score"),
            ranking_signals=item.get("ranking_signals")
        )
        for item in ranked_items[:limit]
    ]
    
    return FeedResponse(
        feed_type=f"ai_ranked_{strategy}",
        items=feed_items,
        total_count=len(feed_items),
        next_cursor=None,
        refresh_timestamp=datetime.utcnow()
    )


@router.post("/track-engagement", summary="Track content engagement")
async def track_content_engagement(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
    content_id: str = Query(..., description="Content item ID"),
    action: str = Query(..., description="Engagement action: view, like, comment, share, complete, skip"),
    duration_seconds: Optional[int] = Query(None, description="Time spent on content")
):
    """
    Track user engagement with content for improving recommendations.
    
    This data is used to:
    - Personalize future feed recommendations
    - Calculate trending scores
    - Improve content quality signals
    
    **Actions:**
    - `view`: User viewed the content
    - `like`: User liked the content
    - `comment`: User commented on content
    - `share`: User shared content
    - `complete`: User completed content (video/course)
    - `skip`: User skipped/dismissed content
    """
    valid_actions = {"view", "like", "comment", "share", "complete", "skip"}
    if action not in valid_actions:
        raise ValidationProblem(f"Invalid action. Must be one of: {valid_actions}")
    
    # Track asynchronously to not block response
    background_tasks.add_task(
        feed_ranking_service.track_engagement,
        db,
        str(current_user.id),
        content_id,
        action,
        {"duration_seconds": duration_seconds} if duration_seconds else None
    )
    
    logger.info(f"Tracking engagement: user={current_user.id}, content={content_id}, action={action}")
    
    return {"success": True, "message": f"Engagement '{action}' recorded"}


@router.put("/preferences", summary="Update feed preferences")
async def update_feed_preferences(
    preferences: RankingPreferencesRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update user's feed ranking preferences.
    
    These preferences influence how content is ranked in personalized feeds.
    """
    # In production, save to user's profile
    profile_data = current_user.profile_data or {}
    profile_data["feed_preferences"] = preferences.model_dump()
    current_user.profile_data = profile_data
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Feed preferences updated",
        "preferences": preferences.model_dump()
    }


@router.get("/explain/{content_id}", summary="Explain content ranking")
async def explain_content_ranking(
    content_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Explain why a content item was recommended.
    
    Provides transparency into the AI ranking signals.
    """
    # Get the content item
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise ResourceNotFoundProblem(f"Content item {content_id} not found")
    
    # Get author
    author_result = await db.execute(
        select(User).where(User.id == item.created_by)
    )
    author = author_result.scalar_one_or_none()
    
    # Build item dict
    item_dict = {
        "id": str(item.id),
        "content_type": item.content_type,
        "title": item.title,
        "created_at": item.created_at,
        "author": {"id": str(author.id) if author else "unknown"},
        "engagement_stats": {
            "views": item.metadata.get("views", 0) if item.metadata else 0,
            "likes": item.metadata.get("likes", 0) if item.metadata else 0,
            "comments": item.metadata.get("comments", 0) if item.metadata else 0
        },
        "metadata": item.metadata or {},
        "tags": item.metadata.get("tags", []) if item.metadata else []
    }
    
    # Calculate ranking scores
    ranked = await feed_ranking_service.rank_feed(
        db=db,
        user_id=str(current_user.id),
        content_items=[item_dict],
        strategy=RankingStrategy.PERSONALIZED
    )
    
    if ranked:
        signals = ranked[0].get("ranking_signals", {})
        score = ranked[0].get("ranking_score", 0)
        
        # Generate human-readable explanations
        explanations = []
        if signals.get("relevance", 0) > 0.5:
            explanations.append("Matches your interests and learning goals")
        if signals.get("author", 0) > 0.5:
            explanations.append("From an author you follow or engage with")
        if signals.get("freshness", 0) > 0.7:
            explanations.append("Recently published content")
        if signals.get("trending", 0) > 0.5:
            explanations.append("Trending content with growing engagement")
        if signals.get("engagement", 0) > 0.5:
            explanations.append("Highly engaging content with strong community response")
        if signals.get("completion", 0) > 0.7:
            explanations.append("High completion rate indicates quality content")
        
        return {
            "content_id": content_id,
            "ranking_score": score,
            "signals": signals,
            "explanations": explanations if explanations else ["Recommended based on general popularity"]
        }
    
    return {
        "content_id": content_id,
        "ranking_score": 0,
        "signals": {},
        "explanations": ["Could not calculate ranking for this item"]
    }
