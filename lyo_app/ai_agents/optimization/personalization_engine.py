"""
Advanced Personalization Engine
User behavior analysis, preference learning, and dynamic content adaptation.
"""

import asyncio
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib

import structlog

# Optional sklearn imports
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    TfidfVectorizer = None
    cosine_similarity = None
    PCA = None
    KMeans = None

# Optional pandas import
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

from lyo_app.learning.models import CourseEnrollment, LessonCompletion
from lyo_app.feeds.models import Post, UserPostInteraction
from lyo_app.community.models import StudyGroup, GroupMembership

logger = structlog.get_logger(__name__)

class LearningStyle(Enum):
    """Learning style classifications."""
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING_WRITING = "reading_writing"
    SOCIAL = "social"
    SOLITARY = "solitary"

class PersonalityType(Enum):
    """Simplified personality types for content adaptation."""
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    PRACTICAL = "practical"
    SOCIAL = "social"

@dataclass
class UserProfile:
    """Comprehensive user profile for personalization."""
    user_id: int
    learning_style: LearningStyle
    personality_type: PersonalityType
    difficulty_preference: float  # 0.0 (easy) to 1.0 (hard)
    interaction_patterns: Dict[str, float] = field(default_factory=dict)
    topic_preferences: Dict[str, float] = field(default_factory=dict)
    optimal_session_length: int = 30  # minutes
    preferred_time_of_day: str = "morning"
    motivation_level: float = 0.7  # 0.0 to 1.0
    current_mood: str = "neutral"
    learning_goals: List[str] = field(default_factory=list)
    
    def to_vector(self) -> np.ndarray:
        """Convert profile to feature vector for ML models."""
        features = [
            hash(self.learning_style.value) % 100 / 100,
            hash(self.personality_type.value) % 100 / 100,
            self.difficulty_preference,
            self.motivation_level,
            len(self.learning_goals) / 10,  # Normalize goal count
            hash(self.preferred_time_of_day) % 100 / 100,
            self.optimal_session_length / 120,  # Normalize to 0-1
        ]
        
        # Add top 5 topic preferences
        top_topics = sorted(self.topic_preferences.items(), key=lambda x: x[1], reverse=True)[:5]
        topic_features = [score for _, score in top_topics]
        topic_features.extend([0.0] * (5 - len(topic_features)))  # Pad to 5
        
        features.extend(topic_features)
        return np.array(features)

@dataclass
class ContentRecommendation:
    """Personalized content recommendation."""
    content_id: str
    content_type: str  # course, lesson, post, group
    title: str
    relevance_score: float
    difficulty_match: float
    style_compatibility: float
    timing_score: float
    personalization_factors: Dict[str, float]
    explanation: str

class BehaviorAnalyzer:
    """Analyze user behavior patterns for personalization."""
    
    def __init__(self):
        self.interaction_weights = {
            "view": 1.0,
            "like": 2.0,
            "comment": 3.0,
            "share": 4.0,
            "complete": 5.0,
            "bookmark": 3.5,
            "download": 4.5
        }
    
    async def analyze_learning_behavior(self, user_id: int, days_back: int = 30) -> Dict[str, Any]:
        """Analyze user's learning behavior patterns."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Analyze course enrollments and completions
            learning_patterns = await self._analyze_learning_patterns(user_id, start_date, end_date)
            
            # Analyze content interactions
            interaction_patterns = await self._analyze_interaction_patterns(user_id, start_date, end_date)
            
            # Analyze time-based patterns
            temporal_patterns = await self._analyze_temporal_patterns(user_id, start_date, end_date)
            
            # Combine insights
            behavior_profile = {
                "learning_velocity": learning_patterns.get("completion_rate", 0.5),
                "preferred_difficulty": learning_patterns.get("avg_difficulty", 0.5),
                "engagement_level": interaction_patterns.get("avg_engagement", 0.5),
                "consistency_score": temporal_patterns.get("consistency", 0.5),
                "preferred_content_types": interaction_patterns.get("content_preferences", {}),
                "optimal_session_time": temporal_patterns.get("optimal_time", "morning"),
                "learning_style_indicators": learning_patterns.get("style_indicators", {}),
            }
            
            return behavior_profile
            
        except Exception as e:
            logger.error(f"Behavior analysis failed for user {user_id}: {e}")
            return self._get_default_behavior_profile()
    
    async def _analyze_learning_patterns(self, user_id: int, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Analyze learning completion patterns."""
        # This would query the database for actual user learning data
        # For now, return simulated analysis
        
        return {
            "completion_rate": 0.75,
            "avg_difficulty": 0.6,
            "style_indicators": {
                "prefers_visual": 0.8,
                "prefers_hands_on": 0.6,
                "prefers_structured": 0.7
            }
        }
    
    async def _analyze_interaction_patterns(self, user_id: int, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Analyze content interaction patterns."""
        # This would analyze actual user interactions
        # For now, return simulated analysis
        
        return {
            "avg_engagement": 0.7,
            "content_preferences": {
                "video": 0.8,
                "text": 0.6,
                "interactive": 0.9,
                "quiz": 0.7
            }
        }
    
    async def _analyze_temporal_patterns(self, user_id: int, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Analyze time-based learning patterns."""
        # This would analyze when users are most active/productive
        # For now, return simulated analysis
        
        return {
            "consistency": 0.8,
            "optimal_time": "morning",
            "session_length_preference": 45
        }
    
    def _get_default_behavior_profile(self) -> Dict[str, Any]:
        """Default behavior profile for new users."""
        return {
            "learning_velocity": 0.5,
            "preferred_difficulty": 0.5,
            "engagement_level": 0.5,
            "consistency_score": 0.5,
            "preferred_content_types": {},
            "optimal_session_time": "morning",
            "learning_style_indicators": {}
        }

class UserEmbeddingModel:
    """Generate user embeddings for similarity and clustering."""
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        self.user_embeddings: Dict[int, np.ndarray] = {}
        self.content_embeddings: Dict[str, np.ndarray] = {}
        
        if SKLEARN_AVAILABLE:
            # Lazy init - initialized in _ensure_models
            self.tfidf_vectorizer = None
            self.pca = None
            self.kmeans = None
        else:
            logger.warning("scikit-learn not available. Personalization features will be limited.")
            self.tfidf_vectorizer = None
            self.pca = None
            self.kmeans = None
            
    def _ensure_models(self):
        """Lazy load ML models."""
        global SKLEARN_AVAILABLE
        
        if not SKLEARN_AVAILABLE:
            return
            
        if self.tfidf_vectorizer is not None:
            return
            
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer as TFIDF
            from sklearn.decomposition import PCA as PCA_CLS
            from sklearn.cluster import KMeans as KMEANS_CLS
            
            logger.info("Initializing personalization ML models...")
            self.tfidf_vectorizer = TFIDF(max_features=1000, stop_words='english')
            self.pca = PCA_CLS(n_components=self.embedding_dim)
            self.kmeans = KMEANS_CLS(n_clusters=10, random_state=42)
            logger.info("Personalization models initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ML models: {e}")
            SKLEARN_AVAILABLE = False
        
    async def generate_user_embedding(self, user_profile: UserProfile, interaction_history: List[Dict]) -> np.ndarray:
        """Generate dense embedding for user based on profile and interactions."""
        try:
            self._ensure_models()
            
            # Start with profile features
            profile_features = user_profile.to_vector()
            
            # Add interaction-based features
            interaction_features = self._extract_interaction_features(interaction_history)
            
            # Combine and normalize
            combined_features = np.concatenate([profile_features, interaction_features])
            
            # Ensure consistent dimensionality
            if len(combined_features) < self.embedding_dim:
                # Pad with zeros
                padding = np.zeros(self.embedding_dim - len(combined_features))
                combined_features = np.concatenate([combined_features, padding])
            elif len(combined_features) > self.embedding_dim:
                # Use PCA to reduce dimensionality if available
                if self.pca:
                    combined_features = self.pca.fit_transform(combined_features.reshape(1, -1))[0]
                else:
                    # Truncate if PCA not available
                    combined_features = combined_features[:self.embedding_dim]
            
            # Cache the embedding
            self.user_embeddings[user_profile.user_id] = combined_features
            
            return combined_features
            
        except Exception as e:
            logger.error(f"User embedding generation failed: {e}")
            return np.random.normal(0, 0.1, self.embedding_dim)
    
    def _extract_interaction_features(self, interaction_history: List[Dict]) -> np.ndarray:
        """Extract features from user interaction history."""
        if not interaction_history:
            return np.zeros(50)  # Default feature size
        
        # Aggregate interaction types
        interaction_counts = {}
        total_time_spent = 0
        content_types = {}
        
        for interaction in interaction_history:
            action = interaction.get("action", "view")
            content_type = interaction.get("content_type", "unknown")
            duration = interaction.get("duration", 0)
            
            interaction_counts[action] = interaction_counts.get(action, 0) + 1
            content_types[content_type] = content_types.get(content_type, 0) + 1
            total_time_spent += duration
        
        # Create feature vector
        features = []
        
        # Interaction type features (normalized)
        total_interactions = len(interaction_history)
        for action_type in ["view", "like", "comment", "share", "complete"]:
            features.append(interaction_counts.get(action_type, 0) / total_interactions)
        
        # Content type preferences (normalized)
        for content_type in ["video", "text", "interactive", "quiz", "discussion"]:
            features.append(content_types.get(content_type, 0) / total_interactions)
        
        # Temporal features
        features.extend([
            total_time_spent / max(total_interactions, 1),  # Avg time per interaction
            len(set(i.get("date", "") for i in interaction_history)),  # Active days
        ])
        
        # Pad to consistent size
        while len(features) < 50:
            features.append(0.0)
        
        return np.array(features[:50])
    
    def find_similar_users(self, user_id: int, top_k: int = 10) -> List[Tuple[int, float]]:
        """Find users similar to the given user."""
        if user_id not in self.user_embeddings:
            return []
        
        user_embedding = self.user_embeddings[user_id]
        similarities = []
        
        for other_user_id, other_embedding in self.user_embeddings.items():
            if other_user_id != user_id:
                similarity = cosine_similarity(
                    user_embedding.reshape(1, -1), 
                    other_embedding.reshape(1, -1)
                )[0][0]
                similarities.append((other_user_id, similarity))
        
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def cluster_users(self) -> Dict[int, int]:
        """Cluster users into similar groups."""
        self._ensure_models()
        
        if len(self.user_embeddings) < 10 or not self.kmeans:
            return {}
        
        user_ids = list(self.user_embeddings.keys())
        embeddings = np.array([self.user_embeddings[uid] for uid in user_ids])
        
        cluster_labels = self.kmeans.fit_predict(embeddings)
        
        return {user_ids[i]: int(cluster_labels[i]) for i in range(len(user_ids))}

class PersonalizationEngine:
    """Main personalization engine coordinating all personalization features."""
    
    def __init__(self):
        self.behavior_analyzer = BehaviorAnalyzer()
        self.embedding_model = UserEmbeddingModel()
        self.user_profiles: Dict[int, UserProfile] = {}
        self.content_popularity: Dict[str, float] = {}
        
        # Personalization weights
        self.recommendation_weights = {
            "relevance": 0.3,
            "difficulty_match": 0.2,
            "style_compatibility": 0.2,
            "timing": 0.1,
            "social_proof": 0.1,
            "novelty": 0.1
        }
    
    async def get_user_profile(self, user_id: int, refresh: bool = False) -> UserProfile:
        """Get or create comprehensive user profile."""
        if user_id in self.user_profiles and not refresh:
            return self.user_profiles[user_id]
        
        # Analyze user behavior
        behavior_data = await self.behavior_analyzer.analyze_learning_behavior(user_id)
        
        # Determine learning style
        learning_style = self._infer_learning_style(behavior_data)
        
        # Determine personality type
        personality_type = self._infer_personality_type(behavior_data)
        
        # Create comprehensive profile
        profile = UserProfile(
            user_id=user_id,
            learning_style=learning_style,
            personality_type=personality_type,
            difficulty_preference=behavior_data.get("preferred_difficulty", 0.5),
            interaction_patterns=behavior_data.get("preferred_content_types", {}),
            optimal_session_length=behavior_data.get("session_length_preference", 30),
            preferred_time_of_day=behavior_data.get("optimal_session_time", "morning"),
            motivation_level=behavior_data.get("engagement_level", 0.7)
        )
        
        # Cache the profile
        self.user_profiles[user_id] = profile
        
        # Generate user embedding
        interaction_history = await self._get_interaction_history(user_id)
        await self.embedding_model.generate_user_embedding(profile, interaction_history)
        
        return profile
    
    async def personalize_content_recommendations(
        self, 
        user_id: int, 
        available_content: List[Dict[str, Any]], 
        num_recommendations: int = 10
    ) -> List[ContentRecommendation]:
        """Generate personalized content recommendations."""
        try:
            # Get user profile
            user_profile = await self.get_user_profile(user_id)
            
            # Score each piece of content
            scored_content = []
            for content in available_content:
                score_breakdown = await self._score_content_for_user(user_profile, content)
                
                recommendation = ContentRecommendation(
                    content_id=content["id"],
                    content_type=content["type"],
                    title=content["title"],
                    relevance_score=score_breakdown["total_score"],
                    difficulty_match=score_breakdown["difficulty_match"],
                    style_compatibility=score_breakdown["style_compatibility"],
                    timing_score=score_breakdown["timing"],
                    personalization_factors=score_breakdown,
                    explanation=self._generate_recommendation_explanation(score_breakdown)
                )
                
                scored_content.append(recommendation)
            
            # Sort by score and return top recommendations
            scored_content.sort(key=lambda x: x.relevance_score, reverse=True)
            return scored_content[:num_recommendations]
            
        except Exception as e:
            logger.error(f"Content personalization failed for user {user_id}: {e}")
            return []
    
    async def _score_content_for_user(self, user_profile: UserProfile, content: Dict[str, Any]) -> Dict[str, float]:
        """Score content relevance for a specific user."""
        scores = {}
        
        # Relevance based on topic preferences
        content_topics = content.get("topics", [])
        relevance_score = 0.0
        for topic in content_topics:
            relevance_score += user_profile.topic_preferences.get(topic, 0.1)
        scores["relevance"] = min(relevance_score / max(len(content_topics), 1), 1.0)
        
        # Difficulty match
        content_difficulty = content.get("difficulty", 0.5)
        difficulty_diff = abs(content_difficulty - user_profile.difficulty_preference)
        scores["difficulty_match"] = 1.0 - difficulty_diff
        
        # Learning style compatibility
        content_format = content.get("format", "text")
        style_compatibility = self._calculate_style_compatibility(user_profile.learning_style, content_format)
        scores["style_compatibility"] = style_compatibility
        
        # Timing score (time of day, session length)
        timing_score = self._calculate_timing_score(user_profile, content)
        scores["timing"] = timing_score
        
        # Social proof (popularity among similar users)
        social_proof = await self._calculate_social_proof(user_profile.user_id, content["id"])
        scores["social_proof"] = social_proof
        
        # Novelty (encourage exploration)
        novelty_score = self._calculate_novelty_score(user_profile, content)
        scores["novelty"] = novelty_score
        
        # Calculate weighted total score
        total_score = sum(
            scores[factor] * self.recommendation_weights[factor]
            for factor in scores
        )
        scores["total_score"] = total_score
        
        return scores
    
    def _infer_learning_style(self, behavior_data: Dict[str, Any]) -> LearningStyle:
        """Infer learning style from behavior patterns."""
        style_indicators = behavior_data.get("learning_style_indicators", {})
        content_prefs = behavior_data.get("preferred_content_types", {})
        
        # Simple heuristics (would be more sophisticated in practice)
        visual_score = content_prefs.get("video", 0) + style_indicators.get("prefers_visual", 0)
        hands_on_score = content_prefs.get("interactive", 0) + style_indicators.get("prefers_hands_on", 0)
        reading_score = content_prefs.get("text", 0)
        
        if visual_score > max(hands_on_score, reading_score):
            return LearningStyle.VISUAL
        elif hands_on_score > reading_score:
            return LearningStyle.KINESTHETIC
        else:
            return LearningStyle.READING_WRITING
    
    def _infer_personality_type(self, behavior_data: Dict[str, Any]) -> PersonalityType:
        """Infer personality type from behavior patterns."""
        # Simple heuristics based on interaction patterns
        engagement = behavior_data.get("engagement_level", 0.5)
        consistency = behavior_data.get("consistency_score", 0.5)
        
        if engagement > 0.7 and consistency > 0.7:
            return PersonalityType.ANALYTICAL
        elif engagement > 0.7:
            return PersonalityType.CREATIVE
        else:
            return PersonalityType.PRACTICAL
    
    def _calculate_style_compatibility(self, learning_style: LearningStyle, content_format: str) -> float:
        """Calculate compatibility between learning style and content format."""
        compatibility_matrix = {
            LearningStyle.VISUAL: {
                "video": 1.0, "image": 0.9, "diagram": 0.9, 
                "text": 0.3, "audio": 0.2, "interactive": 0.7
            },
            LearningStyle.AUDITORY: {
                "audio": 1.0, "video": 0.8, "discussion": 0.9,
                "text": 0.4, "image": 0.2, "interactive": 0.6
            },
            LearningStyle.KINESTHETIC: {
                "interactive": 1.0, "simulation": 0.9, "hands_on": 1.0,
                "text": 0.3, "video": 0.6, "audio": 0.3
            },
            LearningStyle.READING_WRITING: {
                "text": 1.0, "document": 0.9, "article": 0.9,
                "video": 0.5, "audio": 0.3, "interactive": 0.4
            }
        }
        
        style_prefs = compatibility_matrix.get(learning_style, {})
        return style_prefs.get(content_format, 0.5)
    
    def _calculate_timing_score(self, user_profile: UserProfile, content: Dict[str, Any]) -> float:
        """Calculate timing-based scoring."""
        current_hour = datetime.now().hour
        
        # Time of day preferences
        preferred_times = {
            "morning": (6, 12),
            "afternoon": (12, 18),
            "evening": (18, 24),
            "night": (0, 6)
        }
        
        pref_start, pref_end = preferred_times.get(user_profile.preferred_time_of_day, (9, 17))
        
        if pref_start <= current_hour < pref_end:
            time_score = 1.0
        else:
            time_score = 0.5
        
        # Content length vs session preference
        content_duration = content.get("estimated_duration", 30)
        duration_diff = abs(content_duration - user_profile.optimal_session_length)
        duration_score = max(0.0, 1.0 - (duration_diff / user_profile.optimal_session_length))
        
        return (time_score + duration_score) / 2
    
    async def _calculate_social_proof(self, user_id: int, content_id: str) -> float:
        """Calculate social proof score based on similar users' interactions."""
        similar_users = self.embedding_model.find_similar_users(user_id, top_k=20)
        
        if not similar_users:
            return 0.5  # Neutral score
        
        # Check how many similar users engaged with this content
        positive_interactions = 0
        total_similar_users = len(similar_users)
        
        for similar_user_id, similarity in similar_users:
            # This would check actual interaction data
            # For now, simulate based on content popularity
            content_popularity = self.content_popularity.get(content_id, 0.3)
            if content_popularity > 0.5:
                positive_interactions += 1
        
        return positive_interactions / total_similar_users
    
    def _calculate_novelty_score(self, user_profile: UserProfile, content: Dict[str, Any]) -> float:
        """Encourage exploration of new topics/formats."""
        content_topics = set(content.get("topics", []))
        user_topics = set(user_profile.topic_preferences.keys())
        
        # Higher score for content with new topics
        new_topics = content_topics - user_topics
        novelty_ratio = len(new_topics) / max(len(content_topics), 1)
        
        return min(novelty_ratio * 1.5, 1.0)  # Boost novelty but cap at 1.0
    
    def _generate_recommendation_explanation(self, score_breakdown: Dict[str, float]) -> str:
        """Generate human-readable explanation for recommendation."""
        top_factors = sorted(score_breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
        
        explanations = {
            "relevance": "matches your interests",
            "difficulty_match": "is at your preferred difficulty level",
            "style_compatibility": "suits your learning style",
            "timing": "fits your current schedule",
            "social_proof": "is popular with similar learners",
            "novelty": "introduces new topics"
        }
        
        reasons = [explanations.get(factor, factor) for factor, _ in top_factors if factor != "total_score"]
        
        if len(reasons) == 1:
            return f"Recommended because it {reasons[0]}."
        elif len(reasons) == 2:
            return f"Recommended because it {reasons[0]} and {reasons[1]}."
        else:
            return f"Recommended because it {', '.join(reasons[:-1])}, and {reasons[-1]}."
    
    async def _get_interaction_history(self, user_id: int) -> List[Dict]:
        """Get user's interaction history for embedding generation."""
        # This would query actual interaction data
        # For now, return simulated data
        return [
            {"action": "view", "content_type": "video", "duration": 300, "date": "2025-06-20"},
            {"action": "complete", "content_type": "quiz", "duration": 600, "date": "2025-06-21"},
            {"action": "like", "content_type": "article", "duration": 180, "date": "2025-06-22"},
        ]

# Global personalization engine instance
personalization_engine = PersonalizationEngine()
