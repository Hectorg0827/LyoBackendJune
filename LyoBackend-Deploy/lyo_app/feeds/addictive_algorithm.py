"""
TikTok-Style Addictive Feed Algorithm
Ultra-engaging content ranking with psychological addiction patterns
"""

import asyncio
import math
import random
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from lyo_app.core.database import AsyncSession
from lyo_app.feeds.models import FeedItem, UserInteraction
from lyo_app.learning.models import ContentType
from lyo_app.auth.models import User

class EngagementType(str, Enum):
    VIEW = "view"
    LIKE = "like"
    SHARE = "share"
    COMMENT = "comment"
    SAVE = "save"
    COMPLETE = "complete"
    REWATCH = "rewatch"

@dataclass
class FeedWeights:
    """TikTok-style engagement weights for maximum addiction"""
    completion_rate: float = 0.35    # Video completion is king
    watch_time: float = 0.25         # Time spent watching
    rewatches: float = 0.15          # Did they watch again?
    shares: float = 0.10             # Viral coefficient
    likes: float = 0.08              # Basic engagement
    comments: float = 0.05           # Deep engagement
    freshness: float = 0.02          # Recency boost

@dataclass
class UserProfile:
    """Deep user psychological profiling for addiction"""
    attention_span_seconds: float
    preferred_content_types: List[str]
    peak_engagement_hours: List[int]
    dopamine_response_pattern: str  # "quick_hits", "sustained", "variable"
    addiction_level: float  # 0-1 scale
    binge_watching_tendency: float
    curiosity_triggers: List[str]
    emotional_state: str  # "stressed", "bored", "excited", "learning"

class AddictiveFeedAlgorithm:
    """
    TikTok-inspired ultra-addictive feed algorithm with psychological hooks
    
    Key Features:
    - Variable ratio reinforcement (unpredictable rewards)
    - Dopamine spike optimization
    - Attention hijacking techniques
    - Binge-watching optimization
    - Psychological profiling
    """
    
    def __init__(self):
        self.weights = FeedWeights()
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english') if SKLEARN_AVAILABLE else None
        self.content_embeddings = {}
        self.user_profiles = {}
        
        # Psychological manipulation parameters
        self.dopamine_multipliers = {
            "unexpected": 1.8,      # Surprise content
            "cliffhanger": 1.6,     # Incomplete narratives
            "social_proof": 1.4,    # Popular content
            "scarcity": 1.3,        # Limited availability
            "novelty": 1.2          # New content type
        }
        
    async def get_addictive_feed(
        self, 
        user_id: int, 
        feed_type: str,
        limit: int = 20,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """
        Generate ultra-addictive personalized feed
        
        Feed Types:
        - 'home': Main TikTok-style feed (reels/videos)
        - 'stories': 24h disappearing content
        - 'posts': Text/image posts
        - 'courses': Educational content suggestions
        - 'discovery': New user/content suggestions
        """
        
        # Get user psychological profile
        user_profile = await self._get_user_profile(user_id, db)
        
        # Get interaction history for personalization
        interactions = await self._get_user_interactions(user_id, db)
        
        # Generate content candidates (3x more than needed for optimization)
        candidates = await self._get_content_candidates(
            feed_type, limit * 3, user_profile, db
        )
        
        # Apply addiction algorithm
        scored_content = []
        for content in candidates:
            # Calculate base engagement score
            base_score = await self._calculate_engagement_score(content, interactions)
            
            # Apply psychological multipliers
            psych_score = self._apply_psychological_hooks(content, user_profile, base_score)
            
            # Add addiction optimization
            addiction_score = self._optimize_for_addiction(
                content, user_profile, psych_score, interactions
            )
            
            scored_content.append((addiction_score, content))
        
        # Sort by addiction potential
        scored_content.sort(key=lambda x: x[0], reverse=True)
        
        # Apply diversity injection (prevent filter bubbles)
        final_feed = self._inject_diversity(scored_content, user_profile, limit)
        
        # Add psychological triggers
        final_feed = self._add_psychological_triggers(final_feed, user_profile)
        
        # Optimize ordering for maximum addiction
        final_feed = self._optimize_addiction_sequence(final_feed, user_profile)
        
        return final_feed
    
    async def _calculate_engagement_score(
        self, content: Dict[str, Any], interactions: List[Dict[str, Any]]
    ) -> float:
        """Calculate base engagement score with TikTok-style metrics"""
        
        score = 0.0
        views = content.get('views', 1)
        
        # Completion rate (most important for videos)
        if content.get('type') == 'video':
            avg_watch_time = content.get('avg_watch_time', 0)
            duration = content.get('duration', 1)
            completion_rate = min(avg_watch_time / duration, 1.0)
            score += completion_rate * self.weights.completion_rate
            
            # Rewatch bonus (highly addictive indicator)
            rewatches = content.get('rewatches', 0)
            rewatch_rate = rewatches / views if views > 0 else 0
            score += rewatch_rate * self.weights.rewatches
        
        # Engagement metrics
        likes = content.get('likes', 0)
        shares = content.get('shares', 0)
        comments = content.get('comments', 0)
        
        # Viral coefficient
        viral_score = shares / views if views > 0 else 0
        score += viral_score * self.weights.shares
        
        # Engagement rate
        engagement_rate = (likes + comments) / views if views > 0 else 0
        score += engagement_rate * (self.weights.likes + self.weights.comments)
        
        # Freshness with decay
        hours_old = (datetime.utcnow() - content.get('created_at', datetime.utcnow())).total_seconds() / 3600
        freshness = math.exp(-hours_old / 24)  # 24-hour half-life
        score += freshness * self.weights.freshness
        
        return score
    
    def _apply_psychological_hooks(
        self, content: Dict[str, Any], user_profile: UserProfile, base_score: float
    ) -> float:
        """Apply psychological manipulation techniques"""
        
        score = base_score
        
        # Variable ratio reinforcement
        if random.random() < 0.15:  # 15% chance of surprise boost
            score *= self.dopamine_multipliers["unexpected"]
        
        # Social proof amplification
        if content.get('views', 0) > 10000:
            score *= self.dopamine_multipliers["social_proof"]
        
        # Curiosity gap exploitation
        title = content.get('title', '').lower()
        curiosity_words = ['secret', 'hidden', 'nobody knows', 'shocking', 'you won\'t believe']
        if any(word in title for word in curiosity_words):
            score *= self.dopamine_multipliers["cliffhanger"]
        
        # Novelty detection
        content_type = content.get('content_subtype', '')
        if content_type not in user_profile.preferred_content_types:
            score *= self.dopamine_multipliers["novelty"]
        
        # Scarcity manipulation
        if content.get('is_trending', False) or content.get('limited_time', False):
            score *= self.dopamine_multipliers["scarcity"]
        
        return score
    
    def _optimize_for_addiction(
        self, 
        content: Dict[str, Any], 
        user_profile: UserProfile, 
        base_score: float,
        interactions: List[Dict[str, Any]]
    ) -> float:
        """Optimize content for maximum addiction potential"""
        
        score = base_score
        
        # Attention span matching
        content_duration = content.get('duration', 30)
        if content_duration <= user_profile.attention_span_seconds * 1.2:
            score *= 1.3  # Perfect attention span match
        
        # Dopamine response pattern optimization
        if user_profile.dopamine_response_pattern == "quick_hits":
            if content_duration < 30:  # Short, punchy content
                score *= 1.4
        elif user_profile.dopamine_response_pattern == "sustained":
            if 60 < content_duration < 300:  # Longer form content
                score *= 1.3
        
        # Binge-watching optimization
        if user_profile.binge_watching_tendency > 0.7:
            # Boost serialized content or similar creators
            if content.get('is_series', False) or content.get('creator_id') in [
                i.get('creator_id') for i in interactions[-10:]  # Recent interactions
            ]:
                score *= 1.5
        
        # Emotional state targeting
        content_mood = content.get('mood', 'neutral')
        if content_mood == user_profile.emotional_state:
            score *= 1.2
        
        # Peak hours boost
        current_hour = datetime.now().hour
        if current_hour in user_profile.peak_engagement_hours:
            score *= 1.15
        
        return score
    
    def _inject_diversity(
        self, 
        scored_content: List[Tuple[float, Dict[str, Any]]], 
        user_profile: UserProfile, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Inject diversity to prevent filter bubbles while maintaining addiction"""
        
        final_feed = []
        used_creators = set()
        used_topics = set()
        
        # Take top content but ensure diversity
        for score, content in scored_content:
            if len(final_feed) >= limit:
                break
                
            creator_id = content.get('creator_id')
            topic = content.get('primary_topic')
            
            # Diversity rules
            if len(final_feed) > 0:
                # No more than 2 from same creator in top 10
                if creator_id in used_creators and len(final_feed) < 10:
                    if list(used_creators).count(creator_id) >= 2:
                        continue
                
                # Topic diversity every 3-4 items
                if len(final_feed) % 3 == 0 and topic in used_topics:
                    continue
            
            final_feed.append(content)
            used_creators.add(creator_id)
            used_topics.add(topic)
        
        # Fill remaining slots with exploration content (10-20% of feed)
        exploration_count = max(1, limit // 6)
        if len(final_feed) < limit:
            # Add random high-quality content for serendipity
            remaining = [c for _, c in scored_content if c not in final_feed]
            random.shuffle(remaining)
            final_feed.extend(remaining[:limit - len(final_feed)])
        
        return final_feed
    
    def _add_psychological_triggers(
        self, feed: List[Dict[str, Any]], user_profile: UserProfile
    ) -> List[Dict[str, Any]]:
        """Add psychological triggers for maximum engagement"""
        
        for i, content in enumerate(feed):
            # Add position-based triggers
            if i == 0:  # First item - hook them immediately
                content['priority_boost'] = True
                content['trigger'] = 'instant_gratification'
            elif i == len(feed) // 2:  # Middle - prevent drop-off
                content['trigger'] = 'momentum_keeper'
            elif i == len(feed) - 1:  # Last item - create anticipation
                content['trigger'] = 'come_back_tomorrow'
            
            # Add curiosity gaps
            if i % 5 == 4:  # Every 5th item
                content['curiosity_gap'] = True
                content['trigger'] = 'what_happens_next'
            
            # Variable reward timing
            if random.random() < 0.1:  # 10% chance
                content['surprise_reward'] = True
                content['trigger'] = 'unexpected_delight'
        
        return feed
    
    def _optimize_addiction_sequence(
        self, feed: List[Dict[str, Any]], user_profile: UserProfile
    ) -> List[Dict[str, Any]]:
        """Optimize sequence for maximum addiction using psychological principles"""
        
        # Start strong - immediate dopamine hit
        if len(feed) > 2:
            # Move highest engagement content to position 2 (after hook)
            highest_idx = max(range(2, min(6, len(feed))), 
                            key=lambda i: feed[i].get('likes', 0) + feed[i].get('shares', 0))
            if highest_idx != 1:
                feed[1], feed[highest_idx] = feed[highest_idx], feed[1]
        
        # Create dopamine valleys and peaks
        for i in range(2, len(feed), 3):
            if i + 1 < len(feed):
                # Create micro-addiction cycles: good -> great -> good
                if feed[i].get('views', 0) < feed[i + 1].get('views', 0):
                    feed[i], feed[i + 1] = feed[i + 1], feed[i]
        
        # End with cliffhanger for return visit
        if len(feed) > 3:
            # Find content with high share potential for last position
            cliffhanger_candidates = [
                i for i in range(len(feed) - 5, len(feed))
                if feed[i].get('content_type') == 'video' and 
                feed[i].get('duration', 0) > 30
            ]
            
            if cliffhanger_candidates:
                last_idx = len(feed) - 1
                best_cliffhanger = max(cliffhanger_candidates, 
                                     key=lambda i: feed[i].get('shares', 0))
                if best_cliffhanger != last_idx:
                    feed[last_idx], feed[best_cliffhanger] = feed[best_cliffhanger], feed[last_idx]
        
        return feed
    
    async def _get_user_profile(self, user_id: int, db: AsyncSession) -> UserProfile:
        """Get or create deep user psychological profile"""
        
        if user_id in self.user_profiles:
            return self.user_profiles[user_id]
        
        # Create profile from interaction history
        # This would analyze user behavior patterns
        profile = UserProfile(
            attention_span_seconds=45.0,  # Average from user behavior
            preferred_content_types=['video', 'story'],
            peak_engagement_hours=[20, 21, 22],  # 8-10 PM
            dopamine_response_pattern="quick_hits",
            addiction_level=0.6,
            binge_watching_tendency=0.7,
            curiosity_triggers=['tutorial', 'behind_scenes', 'trending'],
            emotional_state="learning"
        )
        
        # Cache profile
        self.user_profiles[user_id] = profile
        return profile
    
    async def _get_user_interactions(self, user_id: int, db: AsyncSession) -> List[Dict[str, Any]]:
        """Get recent user interactions for personalization"""
        
        # This would fetch from database
        # Placeholder implementation
        return []
    
    async def _get_content_candidates(
        self, 
        feed_type: str, 
        limit: int, 
        user_profile: UserProfile,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Get content candidates based on feed type"""
        
        # Placeholder implementation - would fetch from database
        candidates = []
        
        # Generate mock data for different feed types
        if feed_type == 'home':
            # Main TikTok-style video feed
            candidates = self._generate_video_candidates(limit, user_profile)
        elif feed_type == 'stories':
            # 24-hour disappearing content
            candidates = self._generate_story_candidates(limit, user_profile)
        elif feed_type == 'posts':
            # Text and image posts
            candidates = self._generate_post_candidates(limit, user_profile)
        elif feed_type == 'courses':
            # Educational content suggestions
            candidates = self._generate_course_candidates(limit, user_profile)
        elif feed_type == 'discovery':
            # New user and content suggestions
            candidates = self._generate_discovery_candidates(limit, user_profile)
        
        return candidates
    
    def _generate_video_candidates(self, limit: int, user_profile: UserProfile) -> List[Dict[str, Any]]:
        """Generate TikTok-style video candidates"""
        
        candidates = []
        
        for i in range(limit):
            candidate = {
                'id': f'video_{i}',
                'type': 'video',
                'content_subtype': random.choice(['tutorial', 'entertainment', 'educational', 'trending']),
                'title': f'Amazing Video {i}',
                'duration': random.randint(15, 180),
                'views': random.randint(100, 1000000),
                'likes': random.randint(10, 100000),
                'shares': random.randint(1, 10000),
                'comments': random.randint(5, 5000),
                'rewatches': random.randint(0, 1000),
                'avg_watch_time': random.randint(10, 180),
                'creator_id': f'creator_{random.randint(1, 100)}',
                'primary_topic': random.choice(['tech', 'education', 'entertainment', 'lifestyle']),
                'created_at': datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
                'is_trending': random.random() < 0.1,
                'is_series': random.random() < 0.2,
                'mood': random.choice(['excited', 'calm', 'funny', 'educational'])
            }
            candidates.append(candidate)
        
        return candidates
    
    def _generate_story_candidates(self, limit: int, user_profile: UserProfile) -> List[Dict[str, Any]]:
        """Generate story candidates (24h disappearing content)"""
        
        candidates = []
        
        for i in range(limit):
            candidate = {
                'id': f'story_{i}',
                'type': 'story',
                'title': f'Story Update {i}',
                'duration': random.randint(5, 30),
                'views': random.randint(50, 10000),
                'likes': random.randint(5, 1000),
                'creator_id': f'creator_{random.randint(1, 50)}',
                'expires_at': datetime.utcnow() + timedelta(hours=random.randint(1, 24)),
                'created_at': datetime.utcnow() - timedelta(hours=random.randint(1, 23)),
                'is_urgent': random.random() < 0.3,  # FOMO trigger
                'mood': random.choice(['behind_scenes', 'announcement', 'personal', 'educational'])
            }
            candidates.append(candidate)
        
        return candidates
    
    def _generate_post_candidates(self, limit: int, user_profile: UserProfile) -> List[Dict[str, Any]]:
        """Generate text/image post candidates"""
        
        candidates = []
        
        for i in range(limit):
            candidate = {
                'id': f'post_{i}',
                'type': 'post',
                'content_subtype': random.choice(['text', 'image', 'carousel']),
                'title': f'Interesting Post {i}',
                'views': random.randint(20, 50000),
                'likes': random.randint(2, 5000),
                'shares': random.randint(0, 500),
                'comments': random.randint(1, 200),
                'creator_id': f'creator_{random.randint(1, 200)}',
                'primary_topic': random.choice(['tech', 'education', 'lifestyle', 'career']),
                'created_at': datetime.utcnow() - timedelta(hours=random.randint(1, 168)),
                'is_discussion_starter': random.random() < 0.4,
                'mood': random.choice(['informative', 'inspiring', 'question', 'tip'])
            }
            candidates.append(candidate)
        
        return candidates
    
    def _generate_course_candidates(self, limit: int, user_profile: UserProfile) -> List[Dict[str, Any]]:
        """Generate educational course suggestions"""
        
        candidates = []
        
        for i in range(limit):
            candidate = {
                'id': f'course_{i}',
                'type': 'course',
                'title': f'Master Course {i}',
                'duration': random.randint(300, 3600),  # 5 min to 1 hour
                'views': random.randint(100, 100000),
                'enrollments': random.randint(10, 10000),
                'completion_rate': random.uniform(0.3, 0.9),
                'rating': random.uniform(4.0, 5.0),
                'instructor_id': f'instructor_{random.randint(1, 50)}',
                'category': random.choice(['programming', 'design', 'business', 'data_science']),
                'difficulty': random.choice(['beginner', 'intermediate', 'advanced']),
                'created_at': datetime.utcnow() - timedelta(days=random.randint(1, 365)),
                'is_trending': random.random() < 0.15,
                'is_new': random.random() < 0.2,
                'has_certificate': random.random() < 0.7
            }
            candidates.append(candidate)
        
        return candidates
    
    def _generate_discovery_candidates(self, limit: int, user_profile: UserProfile) -> List[Dict[str, Any]]:
        """Generate discovery suggestions (new users, content)"""
        
        candidates = []
        
        for i in range(limit):
            suggestion_type = random.choice(['new_creator', 'trending_topic', 'similar_interests'])
            
            candidate = {
                'id': f'discovery_{i}',
                'type': 'discovery',
                'suggestion_type': suggestion_type,
                'title': f'Discover: {suggestion_type.replace("_", " ").title()} {i}',
                'target_id': f'target_{random.randint(1, 1000)}',
                'relevance_score': random.uniform(0.5, 1.0),
                'social_proof': random.randint(5, 50000),  # followers, likes, etc.
                'novelty_score': random.uniform(0.7, 1.0),
                'created_at': datetime.utcnow() - timedelta(hours=random.randint(1, 48)),
                'is_trending': random.random() < 0.25,
                'category': random.choice(['creator', 'topic', 'community', 'course'])
            }
            candidates.append(candidate)
        
        return candidates

# Global instance
addictive_feed_algorithm = AddictiveFeedAlgorithm()
