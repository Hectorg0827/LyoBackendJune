"""Content curator service for AI-powered content recommendations and management."""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import asyncio

from lyo_app.models.enhanced import User, Course, ContentItem, Task
from lyo_app.models.loading import ModelManager

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    """Types of content that can be curated."""
    COURSE = "course"
    LESSON = "lesson"
    ARTICLE = "article"
    VIDEO = "video"
    QUIZ = "quiz"
    EXERCISE = "exercise"


class CurationStrategy(str, Enum):
    """Strategies for content curation."""
    PERSONALIZED = "personalized"
    TRENDING = "trending" 
    COLLABORATIVE_FILTERING = "collaborative_filtering"
    CONTENT_BASED = "content_based"
    SKILL_GAP_ANALYSIS = "skill_gap_analysis"
    DIFFICULTY_PROGRESSION = "difficulty_progression"


class ContentCurator:
    """
    AI-powered content curator for personalized learning recommendations.
    
    This service uses the Gemma 3 model to analyze user learning patterns,
    preferences, and progress to provide intelligent content recommendations.
    """
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self.logger = logging.getLogger(__name__)
    
    async def get_personalized_recommendations(
        self,
        user_id: str,
        db: AsyncSession,
        content_type: Optional[ContentType] = None,
        limit: int = 10,
        strategy: CurationStrategy = CurationStrategy.PERSONALIZED
    ) -> List[Dict[str, Any]]:
        """
        Get personalized content recommendations for a user.
        
        Args:
            user_id: Target user ID
            db: Database session
            content_type: Optional content type filter
            limit: Maximum number of recommendations
            strategy: Curation strategy to use
        
        Returns:
            List of recommended content items with relevance scores
        """
        try:
            # Get user profile and learning history
            user_profile = await self._build_user_profile(user_id, db)
            
            # Get available content
            available_content = await self._get_available_content(
                db, content_type, user_id
            )
            
            # Apply curation strategy
            if strategy == CurationStrategy.PERSONALIZED:
                recommendations = await self._personalized_curation(
                    user_profile, available_content, limit
                )
            elif strategy == CurationStrategy.TRENDING:
                recommendations = await self._trending_curation(
                    available_content, limit
                )
            elif strategy == CurationStrategy.SKILL_GAP_ANALYSIS:
                recommendations = await self._skill_gap_curation(
                    user_profile, available_content, limit
                )
            else:
                # Fallback to simple recommendation
                recommendations = available_content[:limit]
            
            self.logger.info(f"Generated {len(recommendations)} recommendations for user {user_id}")
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error generating recommendations for user {user_id}: {e}")
            # Fallback to simple content list
            return await self._fallback_recommendations(db, content_type, limit)
    
    async def analyze_content_quality(
        self,
        content_item: ContentItem,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyze the quality and characteristics of a content item.
        
        Args:
            content_item: Content item to analyze
            db: Database session
        
        Returns:
            Quality analysis results including scores and insights
        """
        try:
            # Prepare content for analysis
            analysis_prompt = self._build_content_analysis_prompt(content_item)
            
            # Use Gemma 3 model for analysis
            model = await self.model_manager.get_model()
            analysis_result = await model.analyze_content(analysis_prompt)
            
            # Parse and structure the analysis
            quality_metrics = {
                "overall_quality": analysis_result.get("quality_score", 0.7),
                "readability": analysis_result.get("readability_score", 0.7),
                "engagement": analysis_result.get("engagement_potential", 0.7),
                "accuracy": analysis_result.get("accuracy_score", 0.8),
                "relevance": analysis_result.get("relevance_score", 0.7),
                "difficulty_level": analysis_result.get("difficulty", "intermediate"),
                "topics_covered": analysis_result.get("topics", []),
                "suggested_improvements": analysis_result.get("improvements", []),
                "target_audience": analysis_result.get("audience", "general"),
                "estimated_duration": analysis_result.get("duration_minutes", 30)
            }
            
            # Store analysis results in content metadata
            if not content_item.metadata:
                content_item.metadata = {}
            
            content_item.metadata["quality_analysis"] = quality_metrics
            content_item.metadata["analyzed_at"] = datetime.utcnow().isoformat()
            
            await db.commit()
            
            return quality_metrics
            
        except Exception as e:
            self.logger.error(f"Error analyzing content {content_item.id}: {e}")
            # Return default analysis
            return {
                "overall_quality": 0.5,
                "readability": 0.5,
                "engagement": 0.5,
                "accuracy": 0.5,
                "relevance": 0.5,
                "difficulty_level": "intermediate",
                "topics_covered": [],
                "suggested_improvements": ["Analysis temporarily unavailable"],
                "target_audience": "general",
                "estimated_duration": 30
            }
    
    async def generate_learning_path(
        self,
        user_id: str,
        target_skills: List[str],
        db: AsyncSession,
        difficulty_preference: str = "adaptive"
    ) -> List[Dict[str, Any]]:
        """
        Generate a personalized learning path for specific skills.
        
        Args:
            user_id: Target user ID
            target_skills: List of skills to learn
            db: Database session
            difficulty_preference: Preferred difficulty progression
        
        Returns:
            Ordered list of content items forming a learning path
        """
        try:
            user_profile = await self._build_user_profile(user_id, db)
            
            # Get content related to target skills
            skill_content = await self._get_content_by_skills(
                target_skills, db
            )
            
            # Use AI to create optimal learning sequence
            path_prompt = self._build_learning_path_prompt(
                user_profile, target_skills, skill_content, difficulty_preference
            )
            
            model = await self.model_manager.get_model()
            path_result = await model.generate_learning_path(path_prompt)
            
            # Structure the learning path
            learning_path = []
            for i, item in enumerate(path_result.get("path", [])):
                learning_path.append({
                    "sequence_order": i + 1,
                    "content_id": item.get("content_id"),
                    "title": item.get("title"),
                    "content_type": item.get("type"),
                    "difficulty": item.get("difficulty"),
                    "estimated_duration": item.get("duration_minutes", 30),
                    "prerequisites": item.get("prerequisites", []),
                    "learning_objectives": item.get("objectives", []),
                    "skills_gained": item.get("skills", []),
                    "confidence_score": item.get("relevance_score", 0.8)
                })
            
            return learning_path
            
        except Exception as e:
            self.logger.error(f"Error generating learning path for user {user_id}: {e}")
            # Fallback to simple skill-based content list
            return await self._fallback_learning_path(target_skills, db)
    
    async def curate_daily_feed(
        self,
        user_id: str,
        db: AsyncSession,
        feed_size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Curate a daily personalized content feed for a user.
        
        Args:
            user_id: Target user ID
            db: Database session
            feed_size: Number of items in the feed
        
        Returns:
            Curated list of content items for the daily feed
        """
        try:
            user_profile = await self._build_user_profile(user_id, db)
            
            # Mix different types of content
            feed_composition = {
                "personalized": int(feed_size * 0.4),  # 40% personalized
                "trending": int(feed_size * 0.3),      # 30% trending
                "skill_building": int(feed_size * 0.2), # 20% skill development
                "discovery": int(feed_size * 0.1)       # 10% new/random
            }
            
            daily_feed = []
            
            # Get personalized recommendations
            personalized = await self.get_personalized_recommendations(
                user_id, db, limit=feed_composition["personalized"],
                strategy=CurationStrategy.PERSONALIZED
            )
            daily_feed.extend(personalized)
            
            # Get trending content
            trending = await self.get_personalized_recommendations(
                user_id, db, limit=feed_composition["trending"],
                strategy=CurationStrategy.TRENDING
            )
            daily_feed.extend(trending)
            
            # Get skill-building content
            skill_building = await self.get_personalized_recommendations(
                user_id, db, limit=feed_composition["skill_building"],
                strategy=CurationStrategy.SKILL_GAP_ANALYSIS
            )
            daily_feed.extend(skill_building)
            
            # Add some discovery content
            discovery = await self._get_discovery_content(user_id, db, feed_composition["discovery"])
            daily_feed.extend(discovery)
            
            # Shuffle to create variety while maintaining weights
            import random
            random.shuffle(daily_feed)
            
            return daily_feed[:feed_size]
            
        except Exception as e:
            self.logger.error(f"Error curating daily feed for user {user_id}: {e}")
            return await self._fallback_recommendations(db, None, feed_size)
    
    # Private helper methods
    
    async def _build_user_profile(self, user_id: str, db: AsyncSession) -> Dict[str, Any]:
        """Build a comprehensive user profile for curation."""
        # Get user basic info
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            return {}
        
        # Get learning history
        courses_result = await db.execute(
            select(Course).where(Course.user_id == user_id)
            .order_by(Course.updated_at.desc()).limit(20)
        )
        recent_courses = courses_result.scalars().all()
        
        # Get task completion patterns
        tasks_result = await db.execute(
            select(Task).where(Task.user_id == user_id)
            .order_by(Task.updated_at.desc()).limit(50)
        )
        recent_tasks = tasks_result.scalars().all()
        
        # Build profile
        profile = {
            "user_id": user_id,
            "learning_style": user.profile_data.get("learning_style") if user.profile_data else "visual",
            "skill_level": user.profile_data.get("skill_level", "intermediate") if user.profile_data else "intermediate",
            "interests": user.profile_data.get("interests", []) if user.profile_data else [],
            "completed_courses": len([c for c in recent_courses if c.completion_status == "completed"]),
            "completion_rate": self._calculate_completion_rate(recent_courses),
            "preferred_content_types": self._analyze_content_preferences(recent_courses, recent_tasks),
            "recent_topics": self._extract_recent_topics(recent_courses),
            "difficulty_progression": self._analyze_difficulty_progression(recent_courses),
            "engagement_patterns": self._analyze_engagement_patterns(recent_tasks)
        }
        
        return profile
    
    async def _get_available_content(
        self, 
        db: AsyncSession, 
        content_type: Optional[ContentType], 
        exclude_user_id: str
    ) -> List[ContentItem]:
        """Get available content items for recommendations."""
        query = select(ContentItem).where(ContentItem.is_published == True)
        
        if content_type:
            query = query.where(ContentItem.content_type == content_type.value)
        
        # Exclude content the user has already completed
        # This would be more sophisticated in production
        
        result = await db.execute(query.order_by(ContentItem.updated_at.desc()).limit(100))
        return result.scalars().all()
    
    async def _personalized_curation(
        self,
        user_profile: Dict[str, Any],
        available_content: List[ContentItem],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Apply personalized curation algorithm."""
        try:
            # Use AI model for personalized scoring
            curation_prompt = self._build_personalization_prompt(user_profile, available_content)
            
            model = await self.model_manager.get_model()
            scoring_result = await model.score_content_relevance(curation_prompt)
            
            # Combine AI scores with metadata
            scored_content = []
            for i, content in enumerate(available_content):
                ai_score = scoring_result.get("scores", {}).get(str(content.id), 0.5)
                
                # Calculate composite score
                metadata_score = self._calculate_metadata_score(content, user_profile)
                final_score = (ai_score * 0.7) + (metadata_score * 0.3)
                
                scored_content.append({
                    "content_id": str(content.id),
                    "title": content.title,
                    "content_type": content.content_type,
                    "description": content.description,
                    "score": final_score,
                    "ai_score": ai_score,
                    "metadata_score": metadata_score,
                    "created_at": content.created_at.isoformat(),
                    "metadata": content.metadata or {}
                })
            
            # Sort by score and return top results
            scored_content.sort(key=lambda x: x["score"], reverse=True)
            return scored_content[:limit]
            
        except Exception as e:
            self.logger.error(f"Error in personalized curation: {e}")
            # Fallback to simple scoring
            return self._simple_content_scoring(available_content, limit)
    
    async def _trending_curation(
        self, 
        available_content: List[ContentItem], 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Apply trending-based curation."""
        # Simple trending based on recent activity and engagement
        trending_content = []
        
        for content in available_content:
            engagement_score = 0
            if content.metadata:
                engagement_score = (
                    content.metadata.get("views", 0) * 0.1 +
                    content.metadata.get("likes", 0) * 0.5 +
                    content.metadata.get("shares", 0) * 1.0 +
                    content.metadata.get("comments", 0) * 0.8
                )
            
            # Boost recent content
            days_old = (datetime.utcnow() - content.created_at).days
            recency_boost = max(0, 7 - days_old) * 0.1
            
            trending_score = engagement_score + recency_boost
            
            trending_content.append({
                "content_id": str(content.id),
                "title": content.title,
                "content_type": content.content_type,
                "description": content.description,
                "score": trending_score,
                "engagement_metrics": content.metadata or {},
                "created_at": content.created_at.isoformat()
            })
        
        trending_content.sort(key=lambda x: x["score"], reverse=True)
        return trending_content[:limit]
    
    async def _skill_gap_curation(
        self,
        user_profile: Dict[str, Any],
        available_content: List[ContentItem],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Curate content to fill skill gaps."""
        # Identify skill gaps based on user profile
        user_skills = set(user_profile.get("interests", []))
        completed_topics = set(user_profile.get("recent_topics", []))
        
        skill_gap_content = []
        
        for content in available_content:
            content_topics = set()
            if content.metadata and "topics" in content.metadata:
                content_topics = set(content.metadata["topics"])
            
            # Score based on skill gap relevance
            gap_relevance = len(content_topics - completed_topics) / max(len(content_topics), 1)
            skill_match = len(content_topics & user_skills) / max(len(user_skills), 1)
            
            combined_score = (gap_relevance * 0.6) + (skill_match * 0.4)
            
            if combined_score > 0.1:  # Only include relevant content
                skill_gap_content.append({
                    "content_id": str(content.id),
                    "title": content.title,
                    "content_type": content.content_type,
                    "description": content.description,
                    "score": combined_score,
                    "gap_relevance": gap_relevance,
                    "skill_match": skill_match,
                    "new_topics": list(content_topics - completed_topics),
                    "created_at": content.created_at.isoformat()
                })
        
        skill_gap_content.sort(key=lambda x: x["score"], reverse=True)
        return skill_gap_content[:limit]
    
    def _build_content_analysis_prompt(self, content: ContentItem) -> str:
        """Build prompt for content quality analysis."""
        return f"""
        Analyze the following educational content for quality, engagement, and effectiveness:
        
        Title: {content.title}
        Type: {content.content_type}
        Description: {content.description or "No description"}
        
        Please evaluate:
        1. Overall quality score (0-1)
        2. Readability and clarity
        3. Engagement potential
        4. Educational value
        5. Difficulty level
        6. Target audience
        7. Topics covered
        8. Suggested improvements
        
        Return structured analysis.
        """
    
    def _build_personalization_prompt(self, profile: Dict[str, Any], content: List[ContentItem]) -> str:
        """Build prompt for personalized content scoring."""
        content_summary = "\n".join([
            f"ID: {c.id}, Title: {c.title}, Type: {c.content_type}"
            for c in content[:20]  # Limit for token efficiency
        ])
        
        return f"""
        User Profile:
        - Learning Style: {profile.get('learning_style', 'unknown')}
        - Skill Level: {profile.get('skill_level', 'intermediate')}
        - Interests: {', '.join(profile.get('interests', []))}
        - Completion Rate: {profile.get('completion_rate', 0.5)}
        - Recent Topics: {', '.join(profile.get('recent_topics', []))}
        
        Available Content:
        {content_summary}
        
        Score each content item (0-1) based on relevance to this user's profile.
        Return scores as JSON with content IDs as keys.
        """
    
    def _calculate_metadata_score(self, content: ContentItem, profile: Dict[str, Any]) -> float:
        """Calculate relevance score based on metadata."""
        score = 0.5  # Base score
        
        if content.metadata:
            # Difficulty matching
            content_difficulty = content.metadata.get("difficulty", "intermediate")
            user_level = profile.get("skill_level", "intermediate")
            if content_difficulty == user_level:
                score += 0.2
            
            # Topic relevance
            content_topics = set(content.metadata.get("topics", []))
            user_interests = set(profile.get("interests", []))
            if content_topics & user_interests:
                score += 0.2
            
            # Quality score
            if "quality_analysis" in content.metadata:
                quality = content.metadata["quality_analysis"].get("overall_quality", 0.5)
                score += quality * 0.1
        
        return min(1.0, score)
    
    def _simple_content_scoring(self, content: List[ContentItem], limit: int) -> List[Dict[str, Any]]:
        """Simple fallback scoring method."""
        return [
            {
                "content_id": str(c.id),
                "title": c.title,
                "content_type": c.content_type,
                "description": c.description,
                "score": 0.5,  # Default score
                "created_at": c.created_at.isoformat(),
                "metadata": c.metadata or {}
            }
            for c in content[:limit]
        ]
    
    def _calculate_completion_rate(self, courses: List[Course]) -> float:
        """Calculate user's course completion rate."""
        if not courses:
            return 0.0
        
        completed = len([c for c in courses if c.completion_status == "completed"])
        return completed / len(courses)
    
    def _analyze_content_preferences(self, courses: List[Course], tasks: List[Task]) -> List[str]:
        """Analyze user's preferred content types."""
        # This would be more sophisticated in production
        return ["course", "video", "article"]  # Placeholder
    
    def _extract_recent_topics(self, courses: List[Course]) -> List[str]:
        """Extract topics from recent courses."""
        topics = []
        for course in courses:
            if course.metadata and "topics" in course.metadata:
                topics.extend(course.metadata["topics"])
        return list(set(topics))  # Remove duplicates
    
    def _analyze_difficulty_progression(self, courses: List[Course]) -> str:
        """Analyze user's difficulty progression pattern."""
        # Placeholder - would analyze actual difficulty progression
        return "progressive"
    
    def _analyze_engagement_patterns(self, tasks: List[Task]) -> Dict[str, Any]:
        """Analyze user's engagement patterns."""
        # Placeholder - would analyze task completion patterns, timing, etc.
        return {
            "preferred_session_length": 30,
            "active_hours": [9, 10, 11, 14, 15, 16],
            "completion_streak": 3
        }
    
    async def _get_content_by_skills(self, skills: List[str], db: AsyncSession) -> List[ContentItem]:
        """Get content items related to specific skills."""
        # This would use proper skill tagging in production
        result = await db.execute(
            select(ContentItem).where(ContentItem.is_published == True)
            .limit(50)
        )
        return result.scalars().all()
    
    def _build_learning_path_prompt(
        self, 
        profile: Dict[str, Any], 
        skills: List[str], 
        content: List[ContentItem],
        difficulty: str
    ) -> str:
        """Build prompt for learning path generation."""
        return f"""
        Create an optimal learning path for these skills: {', '.join(skills)}
        
        User Profile: {profile.get('skill_level', 'intermediate')} level
        Difficulty Preference: {difficulty}
        Available Content: {len(content)} items
        
        Order the content items to create an effective learning sequence.
        Consider prerequisites, difficulty progression, and skill building.
        """
    
    async def _fallback_learning_path(self, skills: List[str], db: AsyncSession) -> List[Dict[str, Any]]:
        """Simple fallback learning path."""
        return [
            {
                "sequence_order": 1,
                "title": f"Introduction to {skills[0] if skills else 'Learning'}",
                "content_type": "course",
                "difficulty": "beginner",
                "estimated_duration": 30
            }
        ]
    
    async def _get_discovery_content(self, user_id: str, db: AsyncSession, limit: int) -> List[Dict[str, Any]]:
        """Get discovery content for exploration."""
        # Random recent content for discovery
        result = await db.execute(
            select(ContentItem).where(ContentItem.is_published == True)
            .order_by(func.random()).limit(limit)
        )
        content_items = result.scalars().all()
        
        return [
            {
                "content_id": str(c.id),
                "title": c.title,
                "content_type": c.content_type,
                "description": c.description,
                "score": 0.6,  # Discovery content gets moderate score
                "created_at": c.created_at.isoformat(),
                "metadata": c.metadata or {}
            }
            for c in content_items
        ]
    
    async def _fallback_recommendations(
        self, 
        db: AsyncSession, 
        content_type: Optional[ContentType], 
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback recommendations when AI is unavailable."""
        query = select(ContentItem).where(ContentItem.is_published == True)
        
        if content_type:
            query = query.where(ContentItem.content_type == content_type.value)
        
        result = await db.execute(query.order_by(ContentItem.created_at.desc()).limit(limit))
        content_items = result.scalars().all()
        
        return [
            {
                "content_id": str(c.id),
                "title": c.title,
                "content_type": c.content_type,
                "description": c.description,
                "score": 0.5,
                "created_at": c.created_at.isoformat(),
                "metadata": c.metadata or {}
            }
            for c in content_items
        ]


# Global content curator instance
_content_curator = None


async def get_content_curator() -> ContentCurator:
    """Get the global content curator instance."""
    global _content_curator
    
    if _content_curator is None:
        from lyo_app.models.loading import model_manager
        _content_curator = ContentCurator(model_manager)
    
    return _content_curator
