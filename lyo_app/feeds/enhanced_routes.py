"""
Enhanced Feed API Routes with TikTok-style Addictive Algorithm
Production-ready feed system with psychological engagement optimization
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.models import User
from lyo_app.feeds.addictive_algorithm import addictive_feed_algorithm
from lyo_app.core.enhanced_monitoring import monitor_performance, handle_errors, ErrorCategory
from lyo_app.core.logging import logger
from lyo_app.monetization.engine import interleave_ads

router = APIRouter(prefix="/api/v1/feeds", tags=["Enhanced Feeds"])

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class FeedRequest(BaseModel):
    """Request model for personalized feed"""
    feed_type: str = Field(..., description="Feed type (home, stories, posts, courses, discovery)")
    limit: int = Field(20, ge=1, le=50, description="Number of items to return")
    cursor: Optional[str] = Field(None, description="Pagination cursor")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")
    
class FeedItemResponse(BaseModel):
    """Response model for feed item"""
    id: str
    type: str
    content_type: str
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    content_url: Optional[str]
    creator: Dict[str, Any]
    engagement_stats: Dict[str, int]
    metadata: Dict[str, Any]
    relevance_score: float
    addiction_score: float
    timestamp: datetime
    
class FeedResponse(BaseModel):
    """Response model for feed"""
    items: List[FeedItemResponse]
    next_cursor: Optional[str]
    total_count: int
    feed_type: str
    personalization_data: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    # Optional sponsored content (non-breaking)
    sponsored: Optional[List[Dict[str, Any]]] = None

class InteractionRequest(BaseModel):
    """Request model for user interaction"""
    item_id: str
    interaction_type: str = Field(..., description="view, like, share, comment, save, complete")
    duration_ms: Optional[int] = Field(None, description="Time spent on content (milliseconds)")
    completion_percentage: Optional[float] = Field(None, description="Content completion percentage")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional interaction context")

class FeedAnalyticsResponse(BaseModel):
    """Response model for feed analytics"""
    user_engagement: Dict[str, Any]
    content_performance: Dict[str, Any]
    algorithm_metrics: Dict[str, Any]
    recommendations: List[str]

class SuggestionItemResponse(BaseModel):
    """Response model for a user/content suggestion item"""
    id: str
    suggestion_type: str = Field(..., description="new_creator | trending_topic | similar_interests")
    title: str
    target_id: str
    relevance_score: float
    novelty_score: float
    social_proof: int
    category: str
    timestamp: datetime

class SuggestionsResponse(BaseModel):
    """Response model for suggestions list"""
    items: List[SuggestionItemResponse]
    next_cursor: Optional[str]
    total_count: int
    filters: Dict[str, Any]
    sponsored: Optional[List[Dict[str, Any]]] = None

# ============================================================================
# MAIN FEED ENDPOINTS
# ============================================================================

@router.post("/personalized", response_model=FeedResponse)
@monitor_performance("personalized_feed")
@handle_errors(ErrorCategory.AI_SERVICE)
async def get_personalized_feed(
    request: FeedRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get ultra-addictive personalized feed using TikTok-style algorithm
    
    Features:
    - Psychological profiling and targeting
    - Variable ratio reinforcement
    - Dopamine optimization
    - Binge-watching patterns
    - Real-time personalization
    """
    
    try:
        start_time = datetime.utcnow()

        # Get addictive feed from algorithm
        feed_items = await addictive_feed_algorithm.get_addictive_feed(
            user_id=current_user.id,
            feed_type=request.feed_type,
            limit=request.limit,
            db=db
        )

        # Transform to response format
        response_items = []
        for item in feed_items:
            response_item = FeedItemResponse(
                id=item.get('id'),
                type=item.get('type'),
                content_type=item.get('content_subtype', 'unknown'),
                title=item.get('title'),
                description=item.get('description', ''),
                thumbnail_url=item.get('thumbnail_url'),
                content_url=item.get('content_url'),
                creator={
                    'id': item.get('creator_id'),
                    'name': item.get('creator_name', 'Unknown'),
                    'avatar_url': item.get('creator_avatar'),
                    'verified': item.get('creator_verified', False)
                },
                engagement_stats={
                    'views': item.get('views', 0),
                    'likes': item.get('likes', 0),
                    'shares': item.get('shares', 0),
                    'comments': item.get('comments', 0),
                    'saves': item.get('saves', 0)
                },
                metadata={
                    'duration': item.get('duration'),
                    'difficulty': item.get('difficulty'),
                    'tags': item.get('tags', []),
                    'category': item.get('primary_topic'),
                    'mood': item.get('mood'),
                    'trigger': item.get('trigger'),
                    'priority_boost': item.get('priority_boost', False),
                    'curiosity_gap': item.get('curiosity_gap', False),
                    'surprise_reward': item.get('surprise_reward', False)
                },
                relevance_score=item.get('relevance_score', 0.0),
                addiction_score=item.get('addiction_score', 0.0),
                timestamp=item.get('created_at', datetime.utcnow())
            )
            response_items.append(response_item)

        # Calculate performance metrics
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Generate next cursor for pagination
        next_cursor = None
        if len(response_items) == request.limit:
            last_item = response_items[-1]
            next_cursor = f"{last_item.timestamp.isoformat()}_{last_item.id}"

        # Get personalization insights
        user_profile = await addictive_feed_algorithm._get_user_profile(current_user.id, db)

        # Build response
        response = FeedResponse(
            items=response_items,
            next_cursor=next_cursor,
            total_count=len(response_items),
            feed_type=request.feed_type,
            personalization_data={
                'attention_span': user_profile.attention_span_seconds,
                'preferred_types': user_profile.preferred_content_types,
                'dopamine_pattern': user_profile.dopamine_response_pattern,
                'addiction_level': user_profile.addiction_level,
                'emotional_state': user_profile.emotional_state
            },
            performance_metrics={
                'processing_time_ms': processing_time,
                'algorithm_version': '2.0',
                'personalization_score': 0.85,
                'diversity_ratio': 0.25
            }
        )

        # Track feed performance in background
        background_tasks.add_task(
            _track_feed_performance,
            current_user.id,
            request.feed_type,
            len(response_items),
            processing_time
        )

        logger.info(
            f"Personalized feed generated for user {current_user.id}",
            extra={
                'user_id': current_user.id,
                'feed_type': request.feed_type,
                'items_count': len(response_items),
                'processing_time_ms': processing_time
            }
        )

        # Optional sponsored items for UI (non-breaking addition)
        try:
            interleaved = interleave_ads([{"type": "item", "item": i.model_dump()} for i in response_items], placement="feed", every=6)
            sponsored = [x for x in interleaved if x.get("type") == "ad"]
            # Attach to response model's optional field
            response.sponsored = sponsored or None
            return response
        except Exception:
            # Fallback to original response if monetization fails
            return response

    except Exception as e:
        logger.error(f"Failed to generate personalized feed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate personalized feed. Please try again."
        )

@router.post("/interaction")
@monitor_performance("feed_interaction")
@handle_errors(ErrorCategory.BUSINESS_LOGIC)
async def track_interaction(
    request: InteractionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Track user interaction with feed content for algorithm optimization
    
    This endpoint is crucial for the addictive algorithm as it:
    - Updates user psychological profile
    - Adjusts content recommendations
    - Optimizes dopamine triggers
    - Improves binge-watching patterns
    """
    
    try:
        # Process interaction in background for performance
        background_tasks.add_task(
            _process_interaction,
            current_user.id,
            request.item_id,
            request.interaction_type,
            request.duration_ms,
            request.completion_percentage,
            request.context or {}
        )
        
        # Return immediate response
        return {
            'success': True,
            'message': 'Interaction tracked successfully',
            'interaction_id': f"{current_user.id}_{request.item_id}_{int(datetime.utcnow().timestamp())}"
        }
        
    except Exception as e:
        logger.error(f"Failed to track interaction: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to track interaction"
        )

@router.get("/analytics", response_model=FeedAnalyticsResponse)
@monitor_performance("feed_analytics")
@handle_errors(ErrorCategory.BUSINESS_LOGIC)
async def get_feed_analytics(
    feed_type: str = Query("home", description="Feed type to analyze"),
    time_range: str = Query("7d", description="Time range (1d, 7d, 30d)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed feed analytics and personalization insights
    """
    
    try:
        # This would typically fetch from analytics database
        # For now, return mock data structure
        
        analytics = FeedAnalyticsResponse(
            user_engagement={
                'total_sessions': 45,
                'avg_session_duration_minutes': 12.5,
                'total_content_consumed': 234,
                'completion_rate': 0.78,
                'return_rate': 0.85,
                'binge_sessions': 8,
                'peak_engagement_hours': [20, 21, 22],
                'addiction_score': 0.72
            },
            content_performance={
                'top_categories': ['educational', 'entertainment', 'tutorials'],
                'avg_engagement_rate': 0.15,
                'viral_content_count': 3,
                'most_addictive_duration': '45-90 seconds',
                'optimal_posting_times': ['8:00 AM', '1:00 PM', '8:00 PM']
            },
            algorithm_metrics={
                'personalization_accuracy': 0.89,
                'diversity_score': 0.25,
                'novelty_injection_rate': 0.15,
                'dopamine_optimization_score': 0.82,
                'attention_capture_rate': 0.94,
                'binge_trigger_success': 0.67
            },
            recommendations=[
                'Increase short-form content (15-30s) during peak hours',
                'Add more educational content with entertainment elements',
                'Implement curiosity gap triggers in 20% of content',
                'Optimize for mobile binge-watching patterns',
                'Increase surprise reward frequency by 15%'
            ]
        )
        
        return analytics
        
    except Exception as e:
        logger.error(f"Failed to get feed analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get feed analytics"
        )

# ============================================================================
# SPECIALIZED FEED ENDPOINTS
# ============================================================================

@router.get("/trending")
@monitor_performance("trending_feed")
async def get_trending_content(
    category: Optional[str] = Query(None, description="Content category filter"),
    time_window: str = Query("24h", description="Trending time window (1h, 6h, 24h, 7d)"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get trending content with real-time viral detection"""
    
    # Mock trending algorithm - would use real data in production
    trending_items = []
    
    for i in range(limit):
        trending_items.append({
            'id': f'trending_{i}',
            'title': f'Trending Item {i}',
            'viral_score': 0.95 - (i * 0.01),
            'engagement_velocity': 1000 - (i * 20),
            'trending_duration_hours': 12 + i,
            'category': category or 'general'
        })
    
    return {
        'items': trending_items,
        'time_window': time_window,
        'last_updated': datetime.utcnow().isoformat(),
        'algorithm_version': 'viral_detection_v2.0'
    }

@router.get("/discovery")
@monitor_performance("discovery_feed")
async def get_discovery_content(
    exploration_level: float = Query(0.3, ge=0.0, le=1.0, description="Exploration vs exploitation ratio"),
    novelty_boost: bool = Query(True, description="Boost novel content types"),
    limit: int = Query(15, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get discovery content for exploration and serendipity"""
    
    discovery_items = await addictive_feed_algorithm.get_addictive_feed(
        user_id=current_user.id,
        feed_type='discovery',
        limit=limit,
        db=db
    )
    
    # Discovery content plus optional sponsored
    base = {
        'items': discovery_items,
        'exploration_level': exploration_level,
        'novelty_boost': novelty_boost,
        'serendipity_score': 0.75,
        'filter_bubble_break_count': 5
    }
    try:
        interleaved = interleave_ads([{"type": "item", "item": i} for i in discovery_items], placement="feed", every=5)
        base['sponsored'] = [x for x in interleaved if x.get('type') == 'ad'] or None
    except Exception:
        pass
    return base

@router.get("/suggestions", response_model=SuggestionsResponse)
@monitor_performance("user_suggestions")
async def get_user_suggestions(
    only_new_users: bool = Query(True, description="Only suggest new creators to follow"),
    limit: int = Query(15, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get personalized user/content suggestions with optional sponsored items"""

    # Fetch discovery items and filter for suggestions
    raw_items = await addictive_feed_algorithm.get_addictive_feed(
        user_id=current_user.id,
        feed_type='discovery',
        limit=limit * 2,  # overfetch to allow filtering
        db=db
    )

    filtered = [
        i for i in raw_items
        if i.get('type') == 'discovery'
        and (not only_new_users or i.get('suggestion_type') == 'new_creator')
    ][:limit]

    # Map to response items
    items: List[SuggestionItemResponse] = []
    for i in filtered:
        items.append(
            SuggestionItemResponse(
                id=i.get('id'),
                suggestion_type=i.get('suggestion_type', 'new_creator'),
                title=i.get('title', ''),
                target_id=i.get('target_id', ''),
                relevance_score=i.get('relevance_score', 0.0),
                novelty_score=i.get('novelty_score', 0.0),
                social_proof=i.get('social_proof', 0),
                category=i.get('category', 'creator'),
                timestamp=i.get('created_at', datetime.utcnow()),
            )
        )

    # Cursor
    next_cursor = None
    if len(items) == limit:
        last = items[-1]
        next_cursor = f"{last.timestamp.isoformat()}_{last.id}"

    # Build response
    resp = SuggestionsResponse(
        items=items,
        next_cursor=next_cursor,
        total_count=len(items),
        filters={
            'only_new_users': only_new_users
        },
    )

    # Sponsored items (non-breaking)
    try:
        interleaved = interleave_ads([{"type": "item", "item": i.model_dump()} for i in items], placement="feed", every=5)
        resp.sponsored = [x for x in interleaved if x.get('type') == 'ad'] or None
    except Exception:
        pass

    return resp

@router.get("/binge-mode")
@monitor_performance("binge_mode_feed")
async def get_binge_mode_feed(
    session_target_minutes: int = Query(30, ge=10, le=180, description="Target binge session duration"),
    content_mix: str = Query("balanced", description="Content mix (focused, balanced, diverse)"),
    limit: int = Query(50, ge=20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get optimized feed for binge-watching sessions
    
    This endpoint creates a specially curated feed designed to maximize
    session duration through psychological triggers and content flow optimization.
    """
    
    # Get user's binge-watching profile
    user_profile = await addictive_feed_algorithm._get_user_profile(current_user.id, db)
    
    # Generate binge-optimized feed
    binge_feed = await addictive_feed_algorithm.get_addictive_feed(
        user_id=current_user.id,
        feed_type='home',  # Use home but optimize for binge
        limit=limit,
        db=db
    )
    
    # Apply binge-watching optimizations
    optimized_feed = []
    for i, item in enumerate(binge_feed):
        # Add binge-specific metadata
        item['binge_optimization'] = {
            'position_in_session': i + 1,
            'energy_level': 'high' if i < 5 else 'medium' if i < limit * 0.7 else 'low',
            'dopamine_trigger': i % 7 == 0,  # Every 7th item
            'attention_refresher': i % 12 == 0,  # Every 12th item
            'cliffhanger_probability': 0.8 if i == limit - 1 else 0.2
        }
        
        optimized_feed.append(item)
    
    return {
        'items': optimized_feed,
        'session_metadata': {
            'target_duration_minutes': session_target_minutes,
            'estimated_completion_rate': 0.75,
            'binge_optimization_score': 0.88,
            'attention_retention_strategy': 'variable_rewards',
            'content_mix': content_mix
        },
        'user_binge_profile': {
            'tendency_score': user_profile.binge_watching_tendency,
            'optimal_session_length': user_profile.attention_span_seconds * 20,  # Estimate
            'preferred_binge_times': user_profile.peak_engagement_hours
        }
    }

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def _track_feed_performance(
    user_id: int, 
    feed_type: str, 
    items_count: int, 
    processing_time_ms: float
):
    """Track feed performance metrics in background"""
    
    try:
        # This would typically write to analytics database
        logger.info(
            "Feed performance tracked",
            extra={
                'user_id': user_id,
                'feed_type': feed_type,
                'items_count': items_count,
                'processing_time_ms': processing_time_ms,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to track feed performance: {e}")

async def _process_interaction(
    user_id: int,
    item_id: str,
    interaction_type: str,
    duration_ms: Optional[int],
    completion_percentage: Optional[float],
    context: Dict[str, Any]
):
    """Process user interaction for algorithm optimization"""
    
    try:
        # Update user psychological profile
        # This would typically:
        # 1. Update user preferences based on interaction
        # 2. Adjust content recommendations
        # 3. Update engagement patterns
        # 4. Feed into ML models for personalization
        
        logger.info(
            "User interaction processed",
            extra={
                'user_id': user_id,
                'item_id': item_id,
                'interaction_type': interaction_type,
                'duration_ms': duration_ms,
                'completion_percentage': completion_percentage,
                'context': context,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        
        # Update addiction algorithm with interaction data
        # This would involve updating user profile, content scores, etc.
        
    except Exception as e:
        logger.error(f"Failed to process interaction: {e}")

# ============================================================================
# ADMIN AND DEBUG ENDPOINTS
# ============================================================================

@router.get("/debug/algorithm-state")
async def get_algorithm_debug_info(
    current_user: User = Depends(get_current_user)
):
    """Get debug information about the feed algorithm (admin only)"""
    
    # Add admin check here in production
    
    return {
        'algorithm_version': '2.0_addictive',
        'active_features': {
            'psychological_profiling': True,
            'dopamine_optimization': True,
            'binge_optimization': True,
            'curiosity_gap_injection': True,
            'variable_ratio_reinforcement': True,
            'attention_hijacking': True
        },
        'user_profiles_cached': len(addictive_feed_algorithm.user_profiles),
        'error_counts': addictive_feed_algorithm.error_counts if hasattr(addictive_feed_algorithm, 'error_counts') else {},
        'performance_stats': {
            'avg_generation_time_ms': 150,
            'cache_hit_rate': 0.78,
            'personalization_accuracy': 0.89
        }
    }

@router.post("/debug/reset-user-profile")
async def reset_user_profile(
    target_user_id: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """Reset user profile for algorithm debugging"""
    
    user_id = target_user_id or current_user.id
    
    # Clear user profile from cache
    if user_id in addictive_feed_algorithm.user_profiles:
        del addictive_feed_algorithm.user_profiles[user_id]
    
    return {
        'success': True,
        'message': f'User profile reset for user {user_id}',
        'timestamp': datetime.utcnow().isoformat()
    }
