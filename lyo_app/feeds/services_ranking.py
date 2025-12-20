"""
Ranking service for feed posts.
Implements AI-powered post ranking based on user preferences and engagement.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.core.context_engine import ContextEngine

# Initialize engine once
context_engine = ContextEngine()

async def rank_posts_for_user(
    posts: List[Any], 
    db: Optional[AsyncSession] = None,
    user_id: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None
) -> List[Any]:
    """
    Rank posts for a specific user based on relevance and engagement.
    
    Uses ContextEngine to boost posts relevant to the user's current mode (Student/Professional).
    
    Args:
        posts: List of Post objects to rank
        db: Database session (required for context lookup)
        user_id: ID of the user for personalization
        context: Optional context dict with course_id, lesson_id, etc.
        
    Returns:
        Ranked list of posts
    """
    if not posts:
        return []
        
    # If no user or DB, return default ranking (by date usually)
    if not user_id or not db:
        return posts

    try:
        # 1. Get User Context
        user_context = await context_engine.get_user_context(db, user_id)
        
        # 2. Score posts based on context relevance
        scored_posts = []
        for post in posts:
            score = calculate_engagement_score(post) + calculate_recency_score(post)
            
            # Context Boost
            if user_context != "neutral":
                # Check if post content matches context keywords
                post_content = (getattr(post, 'content', '') or '').lower()
                
                # Get keywords for the active context
                # Map specific contexts like 'student_emergency' to 'student' keys
                base_context = "student" if "student" in user_context else \
                               "professional" if "professional" in user_context else \
                               "hobbyist" if "hobbyist" in user_context else None
                               
                if base_context and base_context in context_engine.context_keywords:
                    keywords = context_engine.context_keywords[base_context]
                    if any(k in post_content for k in keywords):
                        score += 0.5  # Significant boost for context match
            
            scored_posts.append((score, post))
            
        # 3. Sort by score descending
        scored_posts.sort(key=lambda x: x[0], reverse=True)
        
        return [p[1] for p in scored_posts]
        
    except Exception as e:
        # Fallback to original order on error
        print(f"Ranking error: {e}")
        return posts


def calculate_engagement_score(post: Any) -> float:
    """
    Calculate engagement score for a post.
    
    Args:
        post: Post object with reactions and comments
        
    Returns:
        Engagement score (0.0 to 1.0)
    """
    # Simple engagement formula
    # Can be enhanced with more sophisticated metrics
    reaction_count = getattr(post, 'reaction_count', 0) or 0
    comment_count = getattr(post, 'comment_count', 0) or 0
    
    # Weighted score
    score = (reaction_count * 1.0 + comment_count * 2.0) / 100.0
    return min(score, 1.0)


def calculate_recency_score(post: Any) -> float:
    """
    Calculate recency score based on post age.
    
    Args:
        post: Post object with created_at timestamp
        
    Returns:
        Recency score (0.0 to 1.0)
    """
    from datetime import datetime, timedelta
    
    created_at = getattr(post, 'created_at', None)
    if not created_at:
        return 0.5
    
    now = datetime.utcnow()
    age = now - created_at
    
    # Posts less than 1 hour old get full score
    # Score decays over 24 hours
    if age < timedelta(hours=1):
        return 1.0
    elif age < timedelta(hours=24):
        return 1.0 - (age.total_seconds() / (24 * 3600)) * 0.5
    else:
        return 0.5
