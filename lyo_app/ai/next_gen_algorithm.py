"""
Next-Generation Feed Algorithm
=============================

TikTok-beating addictive algorithm with ML-powered personalization,
real-time engagement tracking, and dopamine-optimized content delivery.
"""

import asyncio
import numpy as np
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import redis.asyncio as redis

@dataclass
class ContentItem:
    id: str
    creator_id: str
    content_type: str  # video, image, text, educational
    created_at: datetime
    duration: float  # seconds
    tags: List[str]
    embedding: Optional[np.ndarray] = None
    engagement_score: float = 0.0
    viral_velocity: float = 0.0
    educational_value: float = 0.0

@dataclass
class UserInteraction:
    user_id: str
    content_id: str
    action: str  # view, like, share, comment, skip, complete
    timestamp: datetime
    dwell_time: float
    completion_rate: float
    session_depth: int

class NextGenFeedAlgorithm:
    """
    Advanced feed algorithm that beats TikTok's engagement through:
    1. Real-time dwell time prediction
    2. Educational content optimization
    3. Creator-viewer affinity modeling
    4. Viral velocity detection
    5. Dopamine interval optimization
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.user_embeddings = {}
        self.content_embeddings = {}
        self.creator_scores = defaultdict(float)
        self.session_models = {}
        
        # Algorithm weights (optimized for engagement + education)
        self.weights = {
            'relevance': 0.25,
            'dwell_prediction': 0.30,  # Most important like TikTok
            'viral_velocity': 0.15,
            'creator_affinity': 0.15,
            'educational_value': 0.10,  # Unique advantage
            'freshness': 0.05
        }
    
    async def rank_content(self, user_id: str, candidate_content: List[ContentItem], 
                          session_context: Dict) -> List[Tuple[ContentItem, float]]:
        """
        Rank content using advanced ML features that beat TikTok/Instagram
        """
        user_embedding = await self.get_user_embedding(user_id)
        user_history = await self.get_user_history(user_id, hours=24)
        session_depth = session_context.get('depth', 0)
        
        scored_items = []
        
        for content in candidate_content:
            # Multi-dimensional scoring
            scores = {
                'relevance': await self._calculate_relevance(user_embedding, content),
                'dwell_prediction': await self._predict_dwell_time(user_id, content, user_history),
                'viral_velocity': await self._calculate_viral_velocity(content),
                'creator_affinity': await self._get_creator_affinity(user_id, content.creator_id),
                'educational_value': await self._score_educational_value(content, user_id),
                'freshness': self._calculate_freshness(content)
            }
            
            # Weighted composite score
            final_score = sum(self.weights[key] * scores[key] for key in scores)
            
            # Session-aware adjustments
            final_score = await self._apply_session_adjustments(
                final_score, user_id, content, session_depth
            )
            
            # Exploration vs Exploitation (like TikTok)
            if np.random.random() < 0.12:  # 12% exploration
                final_score *= np.random.uniform(1.3, 2.2)
            
            scored_items.append((content, final_score, scores))
        
        # Sort by score and apply business rules
        ranked_items = sorted(scored_items, key=lambda x: x[1], reverse=True)
        
        # Diversity injection (prevent echo chambers)
        final_ranking = await self._inject_diversity(ranked_items, user_id)
        
        return [(item[0], item[1]) for item in final_ranking]
    
    async def _predict_dwell_time(self, user_id: str, content: ContentItem, 
                                 history: List[UserInteraction]) -> float:
        """
        Predict how long user will engage (key TikTok metric)
        """
        if not history:
            return 0.5  # Default for new users
        
        # User's historical patterns
        avg_dwell = np.mean([h.dwell_time for h in history if h.dwell_time > 0])
        completion_rate = np.mean([h.completion_rate for h in history])
        
        # Content type preferences
        type_preference = len([h for h in history 
                              if h.action == 'complete' and 
                              h.content_id.startswith(content.content_type)]) / len(history)
        
        # Time of day patterns
        current_hour = datetime.now().hour
        hour_engagement = await self._get_hour_engagement(user_id, current_hour)
        
        # Creator familiarity
        creator_interactions = len([h for h in history 
                                   if h.content_id.startswith(content.creator_id)])
        creator_familiarity = min(creator_interactions / 10.0, 1.0)
        
        # ML prediction (simplified)
        predicted_dwell = (
            0.4 * (avg_dwell / content.duration) +
            0.3 * completion_rate +
            0.2 * type_preference +
            0.1 * hour_engagement
        ) * (1 + 0.2 * creator_familiarity)
        
        return min(predicted_dwell, 1.0)
    
    async def _calculate_viral_velocity(self, content: ContentItem) -> float:
        """
        Calculate viral potential with time decay (TikTok-style)
        """
        age_hours = (datetime.now() - content.created_at).total_seconds() / 3600
        
        # Get engagement metrics from last 6 hours
        engagement_data = await self.redis.hget(
            f"content:engagement:{content.id}", 
            "recent_metrics"
        )
        
        if not engagement_data:
            return 0.1  # New content gets small boost
        
        # Parse engagement (likes, shares, comments per hour)
        metrics = eval(engagement_data.decode())  # In production, use JSON
        recent_engagement = sum(metrics.values())
        
        # Exponential decay for viral content
        decay_factor = np.exp(-age_hours / 6.0)  # 6-hour half-life
        velocity = (recent_engagement / max(age_hours, 0.1)) * decay_factor
        
        # Normalize to 0-1 scale
        return min(velocity / 100.0, 1.0)
    
    async def _score_educational_value(self, content: ContentItem, user_id: str) -> float:
        """
        Score educational content (our unique advantage over TikTok/Instagram)
        """
        if content.content_type != 'educational':
            return 0.0
        
        # User's learning preferences
        learning_level = await self.redis.get(f"user:learning_level:{user_id}")
        if learning_level:
            level = float(learning_level.decode())
        else:
            level = 0.5  # Default intermediate
        
        # Content difficulty matching
        difficulty_match = 1.0 - abs(content.educational_value - level)
        
        # Learning streak bonus
        streak = await self.redis.get(f"user:learning_streak:{user_id}")
        streak_bonus = min(int(streak.decode()) / 30.0, 0.3) if streak else 0
        
        return difficulty_match + streak_bonus
    
    async def _apply_session_adjustments(self, base_score: float, user_id: str,
                                       content: ContentItem, session_depth: int) -> float:
        """
        Adjust scores based on session context (TikTok's secret sauce)
        """
        # Deeper in session = more variety needed
        variety_bonus = 0
        if session_depth > 5:
            recent_types = await self._get_recent_content_types(user_id, 5)
            if content.content_type not in recent_types:
                variety_bonus = 0.2
        
        # Time-of-day adjustments
        current_hour = datetime.now().hour
        if 6 <= current_hour <= 9:  # Morning: educational content boost
            if content.content_type == 'educational':
                base_score *= 1.3
        elif 20 <= current_hour <= 23:  # Evening: entertainment boost
            if content.content_type in ['video', 'meme']:
                base_score *= 1.2
        
        return base_score + variety_bonus
    
    async def _inject_diversity(self, ranked_items: List, user_id: str) -> List:
        """
        Inject diversity to prevent echo chambers (better than TikTok)
        """
        if len(ranked_items) < 10:
            return ranked_items
        
        final_list = []
        content_types_seen = set()
        creators_seen = set()
        
        for item, score, detailed_scores in ranked_items:
            # Ensure diversity every 3 items
            if (len(final_list) % 3 == 2 and 
                item.content_type in content_types_seen and 
                item.creator_id in creators_seen):
                continue  # Skip for diversity
            
            final_list.append((item, score, detailed_scores))
            content_types_seen.add(item.content_type)
            creators_seen.add(item.creator_id)
            
            if len(final_list) >= 20:  # Limit initial batch
                break
        
        return final_list
    
    async def record_interaction(self, interaction: UserInteraction):
        """
        Record user interaction for algorithm learning
        """
        # Update real-time engagement
        await self.redis.hincrby(
            f"content:engagement:{interaction.content_id}",
            interaction.action,
            1
        )
        
        # Update user preferences
        await self._update_user_embedding(interaction)
        
        # Track session patterns
        await self._update_session_model(interaction)
    
    async def get_user_embedding(self, user_id: str) -> np.ndarray:
        """
        Get or generate user interest embedding
        """
        if user_id in self.user_embeddings:
            return self.user_embeddings[user_id]
        
        # Generate from user history
        history = await self.get_user_history(user_id, hours=168)  # 1 week
        if not history:
            # Random embedding for new users
            embedding = np.random.normal(0, 0.1, 128)
        else:
            # Aggregate from interactions
            embedding = await self._generate_user_embedding_from_history(history)
        
        self.user_embeddings[user_id] = embedding
        return embedding
    
    async def get_user_history(self, user_id: str, hours: int = 24) -> List[UserInteraction]:
        """
        Get user interaction history
        """
        # In production, query from database
        # This is a simplified version
        history_key = f"user:history:{user_id}"
        history_data = await self.redis.lrange(history_key, 0, 100)
        
        interactions = []
        cutoff = datetime.now() - timedelta(hours=hours)
        
        for data in history_data:
            # Parse interaction data
            interaction_dict = eval(data.decode())  # Use JSON in production
            interaction_time = datetime.fromisoformat(interaction_dict['timestamp'])
            
            if interaction_time > cutoff:
                interactions.append(UserInteraction(**interaction_dict))
        
        return interactions
    
    # Helper methods (simplified implementations)
    async def _calculate_relevance(self, user_emb: np.ndarray, content: ContentItem) -> float:
        if content.embedding is None:
            return 0.5
        return cosine_similarity([user_emb], [content.embedding])[0][0]
    
    async def _get_creator_affinity(self, user_id: str, creator_id: str) -> float:
        follows = await self.redis.sismember(f"user:following:{user_id}", creator_id)
        interactions = await self.redis.get(f"user:creator_interactions:{user_id}:{creator_id}")
        
        base_affinity = 0.8 if follows else 0.3
        interaction_bonus = min(int(interactions or 0) / 50.0, 0.5)
        
        return base_affinity + interaction_bonus
    
    def _calculate_freshness(self, content: ContentItem) -> float:
        age_hours = (datetime.now() - content.created_at).total_seconds() / 3600
        return max(0, 1.0 - (age_hours / 24.0))  # Linear decay over 24h
    
    async def _get_hour_engagement(self, user_id: str, hour: int) -> float:
        engagement_key = f"user:hour_engagement:{user_id}"
        hour_data = await self.redis.hget(engagement_key, str(hour))
        return float(hour_data.decode()) if hour_data else 0.5
    
    async def _get_recent_content_types(self, user_id: str, count: int) -> List[str]:
        recent_key = f"user:recent_content_types:{user_id}"
        return [t.decode() for t in await self.redis.lrange(recent_key, 0, count-1)]
    
    async def _update_user_embedding(self, interaction: UserInteraction):
        """Update user embedding based on interaction"""
        # Simplified - in production, use proper ML updating
        pass
    
    async def _update_session_model(self, interaction: UserInteraction):
        """Update session behavior model"""
        pass
    
    async def _generate_user_embedding_from_history(self, history: List[UserInteraction]) -> np.ndarray:
        """Generate user embedding from interaction history"""
        # Simplified - would use proper ML in production
        return np.random.normal(0, 0.1, 128)


class EngagementTracker:
    """
    Track real-time engagement metrics that beat TikTok
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def track_dwell_time(self, user_id: str, content_id: str, dwell_time: float):
        """Track how long user viewed content"""
        await self.redis.lpush(
            f"dwell_times:{content_id}",
            f"{user_id}:{dwell_time}:{datetime.now().isoformat()}"
        )
        
        # Keep only recent data
        await self.redis.ltrim(f"dwell_times:{content_id}", 0, 999)
    
    async def track_completion_rate(self, user_id: str, content_id: str, 
                                  completion_rate: float):
        """Track video/content completion rate"""
        await self.redis.hset(
            f"completion:{content_id}",
            user_id,
            completion_rate
        )
    
    async def track_session_depth(self, user_id: str):
        """Track how deep user goes in session"""
        session_key = f"session:{user_id}:{datetime.now().date()}"
        current_depth = await self.redis.incr(session_key)
        await self.redis.expire(session_key, 86400)  # 24 hours
        return current_depth
    
    async def get_viral_metrics(self, content_id: str) -> Dict[str, float]:
        """Get real-time viral metrics"""
        engagement_key = f"content:engagement:{content_id}"
        metrics = await self.redis.hgetall(engagement_key)
        
        return {
            key.decode(): float(value.decode())
            for key, value in metrics.items()
        }
