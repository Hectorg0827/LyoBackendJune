"""
Feed Ranking Agent - Intelligent Content Feed Personalization

This agent provides intelligent feed ranking and personalization:
- Content relevance scoring based on user behavior and preferences
- Adaptive feed composition for learning effectiveness
- Exploration-exploitation balancing
- User engagement optimization
- Diverse content type selection for learning effectiveness
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload
import numpy as np
from collections import defaultdict

from .models import UserEngagementState, UserEngagementStateEnum, AIModelTypeEnum, AIConversationLog
from .orchestrator import ai_orchestrator, ModelType, TaskComplexity
from lyo_app.feeds.models import Post, PostReaction, FeedItem
from lyo_app.learning.models import CourseEnrollment, LessonCompletion
from lyo_app.auth.models import User

logger = logging.getLogger(__name__)


class FeedRankingAgent:
    """
    Intelligent agent for content feed ranking and personalization.
    """
    
    def __init__(self):
        self.content_cache = {}
        self.user_profiles = {}
        self.model_version = "1.0.0"
        self.last_retrained = datetime.utcnow()
        
    async def rank_feed_items(
        self, 
        user_id: int, 
        content_items: List[Dict[str, Any]], 
        db: AsyncSession,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank feed content items based on user preferences, engagement state, and learning goals.
        
        Args:
            user_id: The ID of the user
            content_items: List of content items to rank
            db: Database session
            context: Additional context (current activity, time of day, etc.)
            
        Returns:
            Ranked list of content items with relevance scores
        """
        start_time = time.time()
        logger.info(f"Ranking feed for user {user_id} with {len(content_items)} items")
        
        if not content_items:
            return []
        
        try:
            # 1. Fetch user data
            user_data = await self._get_user_profile(user_id, db)
            engagement_state = await self._get_engagement_state(user_id, db)
            learning_progress = await self._get_learning_progress(user_id, db)
            content_history = await self._get_content_interaction_history(user_id, db)
            
            # 2. Calculate base relevance scores
            scored_items = await self._calculate_base_relevance(
                user_id=user_id,
                content_items=content_items,
                user_data=user_data,
                engagement_state=engagement_state,
                learning_progress=learning_progress,
                content_history=content_history,
                context=context or {}
            )
            
            # 3. Apply AI personalization if needed for complex decisions
            if self._should_apply_ai_personalization(user_id, engagement_state, scored_items):
                scored_items = await self._apply_ai_personalization(
                    user_id=user_id,
                    scored_items=scored_items,
                    engagement_state=engagement_state,
                    context=context or {}
                )
            
            # 4. Apply diversity and exploration adjustments
            final_ranked_items = self._apply_diversity_and_exploration(
                user_id=user_id, 
                scored_items=scored_items,
                engagement_state=engagement_state
            )
            
            # 5. Log ranking event
            await self._log_ranking_event(
                user_id=user_id,
                ranked_items=final_ranked_items,
                processing_time=time.time() - start_time,
                db=db
            )
            
            logger.info(f"Feed ranking completed for user {user_id} in {time.time() - start_time:.2f}s")
            return final_ranked_items
            
        except Exception as e:
            logger.error(f"Error ranking feed for user {user_id}: {str(e)}", exc_info=True)
            # In case of error, return unranked items as fallback
            return [{**item, "relevance_score": 0.5, "ai_ranked": False} for item in content_items]
    
    async def _get_user_profile(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Fetch user profile data including preferences."""
        try:
            # Cache user profiles for 15 minutes to reduce database load
            if user_id in self.user_profiles and self.user_profiles[user_id]["expires_at"] > datetime.utcnow():
                return self.user_profiles[user_id]["data"]
            
            # Get user and their preferences
            user = (await db.execute(
                select(User)
                .options(selectinload(User.preferences))
                .where(User.id == user_id)
            )).scalar_one_or_none()
            
            if not user:
                return {"error": "User not found"}
            
            # Get user preferences
            preferences = {}
            if hasattr(user, "preferences") and user.preferences:
                preferences = user.preferences.settings if hasattr(user.preferences, "settings") else {}
            
            # Build profile
            profile = {
                "id": user.id,
                "username": user.username,
                "created_at": user.created_at,
                "preferences": preferences,
                "experience_level": user.experience_level if hasattr(user, "experience_level") else "beginner",
                "last_active": user.last_active if hasattr(user, "last_active") else datetime.utcnow(),
            }
            
            # Cache profile
            self.user_profiles[user_id] = {
                "data": profile,
                "expires_at": datetime.utcnow() + timedelta(minutes=15)
            }
            
            return profile
        except Exception as e:
            logger.error(f"Error fetching user profile for {user_id}: {str(e)}")
            return {"id": user_id, "error": str(e)}
    
    async def _get_engagement_state(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Fetch current user engagement state."""
        try:
            state = (await db.execute(
                select(UserEngagementState)
                .where(UserEngagementState.user_id == user_id)
            )).scalar_one_or_none()
            
            if not state:
                return {
                    "state": UserEngagementStateEnum.IDLE,
                    "sentiment_score": 0.0,
                    "confidence_score": 0.0
                }
            
            return {
                "state": state.state,
                "sentiment_score": state.sentiment_score,
                "confidence_score": state.confidence_score,
                "context": state.context,
                "activity_count": state.activity_count,
                "consecutive_struggles": state.consecutive_struggles,
                "last_analyzed_at": state.last_analyzed_at
            }
        except Exception as e:
            logger.error(f"Error fetching engagement state for {user_id}: {str(e)}")
            return {"state": UserEngagementStateEnum.IDLE, "error": str(e)}
    
    async def _get_learning_progress(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Fetch user learning progress data."""
        try:
            # Query user course enrollments
            enrollments = (await db.execute(
                select(CourseEnrollment)
                .where(CourseEnrollment.user_id == user_id)
                .order_by(desc(CourseEnrollment.enrolled_at))
                .limit(100)  # Limit to recent enrollments
            )).scalars().all()
            
            # Query lesson completions
            completions = (await db.execute(
                select(LessonCompletion)
                .where(LessonCompletion.user_id == user_id)
                .order_by(desc(LessonCompletion.completed_at))
                .limit(200)  # Recent completions
            )).scalars().all()
            
            # Organize by course
            courses = {}
            for enrollment in enrollments:
                courses[enrollment.course_id] = {
                    "course_id": enrollment.course_id,
                    "progress_percentage": enrollment.progress_percentage,
                    "enrolled_at": enrollment.enrolled_at,
                    "completed_at": enrollment.completed_at,
                    "is_active": enrollment.is_active,
                }
            
            # Get current/active courses
            active_courses = [c for c in courses.values() 
                             if c["is_active"] and c["progress_percentage"] < 100]
            
            # Get recently completed courses
            completed_courses = [c for c in courses.values() 
                                if c["progress_percentage"] >= 100]
            
            return {
                "courses": courses,
                "active_courses": active_courses,
                "completed_courses": completed_courses,
                "total_courses": len(courses),
                "avg_completion": sum(c["progress_percentage"] for c in courses.values()) / max(len(courses), 1)
            }
        except Exception as e:
            logger.error(f"Error fetching learning progress for {user_id}: {str(e)}")
            return {"modules": {}, "active_modules": [], "error": str(e)}

    async def _get_content_interaction_history(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Fetch user's content interaction history."""
        try:
            # Get recent interactions
            interactions = (await db.execute(
                select(UserContentInteraction)
                .where(UserContentInteraction.user_id == user_id)
                .order_by(desc(UserContentInteraction.timestamp))
                .limit(50)  # Limit to recent interactions
            )).scalars().all()
            
            # Organize by content_id
            by_content = {}
            for interaction in interactions:
                if interaction.content_id not in by_content:
                    by_content[interaction.content_id] = []
                by_content[interaction.content_id].append({
                    "interaction_type": interaction.interaction_type,
                    "timestamp": interaction.timestamp,
                    "duration": interaction.duration if hasattr(interaction, "duration") else None,
                    "reaction": interaction.reaction if hasattr(interaction, "reaction") else None,
                    "metadata": interaction.metadata if hasattr(interaction, "metadata") else {}
                })
            
            # Get viewed content IDs for filtering duplication
            viewed_content_ids = list(by_content.keys())
            
            # Calculate content type preferences
            content_type_counts = defaultdict(int)
            for interaction in interactions:
                if hasattr(interaction, "content_type") and interaction.content_type:
                    content_type_counts[interaction.content_type] += 1
            
            # Calculate topic preferences
            topic_counts = defaultdict(int)
            for interaction in interactions:
                if hasattr(interaction, "metadata") and interaction.metadata:
                    topics = interaction.metadata.get("topics", [])
                    for topic in topics:
                        topic_counts[topic] += 1
            
            return {
                "interactions": by_content,
                "viewed_content_ids": viewed_content_ids,
                "content_type_preferences": dict(content_type_counts),
                "topic_preferences": dict(topic_counts),
                "total_interactions": len(interactions)
            }
        except Exception as e:
            logger.error(f"Error fetching interaction history for {user_id}: {str(e)}")
            return {"interactions": {}, "viewed_content_ids": [], "error": str(e)}
    
    async def _calculate_base_relevance(
        self, 
        user_id: int,
        content_items: List[Dict[str, Any]],
        user_data: Dict[str, Any],
        engagement_state: Dict[str, Any],
        learning_progress: Dict[str, Any],
        content_history: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Calculate base relevance scores for content items."""
        scored_items = []
        
        # Extract user preferences
        preferences = user_data.get("preferences", {})
        topic_preferences = content_history.get("topic_preferences", {})
        content_type_preferences = content_history.get("content_type_preferences", {})
        viewed_content_ids = content_history.get("viewed_content_ids", [])
        
        # Get active learning modules
        active_modules = learning_progress.get("active_modules", [])
        active_module_ids = [m["module_id"] for m in active_modules]
        
        for item in content_items:
            # Skip already viewed content unless it's explicitly needed
            if str(item.get("id")) in viewed_content_ids and not context.get("include_viewed", False):
                continue
                
            # Initialize score components
            score_components = {
                "topic_relevance": 0.0,
                "recency": 0.0,
                "popularity": 0.0,
                "learning_path_relevance": 0.0,
                "type_preference": 0.0,
                "difficulty_match": 0.0,
                "engagement_state_match": 0.0
            }
            
            # 1. Topic relevance
            item_topics = item.get("metadata", {}).get("topics", [])
            if item_topics:
                topic_scores = [topic_preferences.get(topic, 0.1) for topic in item_topics]
                score_components["topic_relevance"] = sum(topic_scores) / len(item_topics)
            
            # 2. Content type preference
            content_type = item.get("content_type", "")
            if content_type:
                type_count = content_type_preferences.get(content_type, 0)
                total_counts = sum(content_type_preferences.values()) or 1
                score_components["type_preference"] = type_count / total_counts
            
            # 3. Recency factor (newer = higher score)
            if "created_at" in item:
                days_old = (datetime.utcnow() - item["created_at"]).days
                score_components["recency"] = max(0, 1 - (days_old / 30))  # Scale by 30 days
            
            # 4. Popularity factor
            score_components["popularity"] = min(1.0, (item.get("view_count", 0) / 1000))
            
            # 5. Learning path relevance
            if "module_id" in item and item["module_id"] in active_module_ids:
                score_components["learning_path_relevance"] = 1.0
                
            # 6. Difficulty match
            user_level = user_data.get("experience_level", "beginner")
            item_level = item.get("difficulty", "intermediate")
            
            level_map = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
            user_level_num = level_map.get(user_level, 1)
            item_level_num = level_map.get(item_level, 2)
            
            level_diff = abs(user_level_num - item_level_num)
            score_components["difficulty_match"] = 1.0 - (level_diff / 3)
            
            # 7. Engagement state matching
            current_state = engagement_state.get("state", UserEngagementStateEnum.IDLE)
            
            # Match content types to engagement states
            state_content_matches = {
                UserEngagementStateEnum.STRUGGLING: ["tutorial", "explanation"],
                UserEngagementStateEnum.BORED: ["challenge", "quiz", "interactive"],
                UserEngagementStateEnum.CURIOUS: ["deep_dive", "advanced_topic"],
                UserEngagementStateEnum.ENGAGED: ["project", "exercise"],
                UserEngagementStateEnum.FRUSTRATED: ["beginner_friendly", "step_by_step"],
                UserEngagementStateEnum.CONFIDENT: ["advanced_topic", "expert_challenge"]
            }
            
            if content_type in state_content_matches.get(current_state, []):
                score_components["engagement_state_match"] = 1.0
            
            # Calculate weighted final score
            weights = {
                "topic_relevance": 0.25,
                "recency": 0.10,
                "popularity": 0.05,
                "learning_path_relevance": 0.30,
                "type_preference": 0.15,
                "difficulty_match": 0.05,
                "engagement_state_match": 0.10
            }
            
            # Custom weights based on engagement state
            if current_state == UserEngagementStateEnum.STRUGGLING:
                weights["difficulty_match"] = 0.15
                weights["learning_path_relevance"] = 0.40
                weights["topic_relevance"] = 0.15
            elif current_state == UserEngagementStateEnum.BORED:
                weights["topic_relevance"] = 0.35
                weights["engagement_state_match"] = 0.20
                weights["learning_path_relevance"] = 0.15
            
            # Calculate final score
            final_score = sum(score * weights[component] for component, score in score_components.items())
            
            # Prepare ranked item
            ranked_item = {
                **item,
                "relevance_score": final_score,
                "score_components": score_components,
                "ai_ranked": True
            }
            
            scored_items.append(ranked_item)
        
        # Sort by relevance score
        scored_items.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored_items
    
    def _should_apply_ai_personalization(
        self, 
        user_id: int, 
        engagement_state: Dict[str, Any], 
        scored_items: List[Dict[str, Any]]
    ) -> bool:
        """Determine if advanced AI personalization should be applied."""
        # Apply AI personalization if:
        # 1. User is struggling or in a critical engagement state
        if engagement_state.get("state") in [UserEngagementStateEnum.STRUGGLING, 
                                           UserEngagementStateEnum.FRUSTRATED]:
            return True
        
        # 2. User has consecutive struggles
        if engagement_state.get("consecutive_struggles", 0) >= 2:
            return True
            
        # 3. There are many similar-scored items needing better differentiation
        if len(scored_items) >= 10:
            top_scores = [item["relevance_score"] for item in scored_items[:5]]
            if max(top_scores) - min(top_scores) < 0.1:  # Very similar scores
                return True
                
        # 4. User has been inactive or disengaged
        last_analyzed = engagement_state.get("last_analyzed_at")
        if last_analyzed and (datetime.utcnow() - last_analyzed) > timedelta(days=7):
            return True
            
        # Default: Use basic ranking
        return False
    
    async def _apply_ai_personalization(
        self,
        user_id: int,
        scored_items: List[Dict[str, Any]],
        engagement_state: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply AI personalization to scored items using orchestrator."""
        try:
            # Only personalize top N items for efficiency
            top_items = scored_items[:10]
            remaining_items = scored_items[10:]
            
            # If very few items, skip AI processing
            if len(top_items) <= 3:
                return scored_items
                
            # Prepare the prompt for AI ranking
            current_state = engagement_state.get("state", "idle")
            sentiment_score = engagement_state.get("sentiment_score", 0)
            
            prompt = f"""
            As an educational content recommendation system, re-rank these content items 
            for a user in the '{current_state}' state with sentiment score {sentiment_score}.
            
            User context:
            - Current state: {current_state}
            - Sentiment: {sentiment_score}
            - Context: {context.get('current_activity', 'browsing')}
            
            Content items to rank:
            {json.dumps([{
                'id': item.get('id'),
                'title': item.get('title'),
                'content_type': item.get('content_type'),
                'difficulty': item.get('difficulty', 'intermediate'),
                'topics': item.get('metadata', {}).get('topics', []),
                'current_score': item.get('relevance_score')
            } for item in top_items], indent=2)}
            
            Re-rank these items to maximize educational value and engagement.
            Return only a JSON array of item IDs in ranked order with short explanations.
            """
            
            # Use orchestrator to get AI response with appropriate model
            response = await ai_orchestrator.generate_response(
                prompt=prompt,
                user_id=user_id,
                task_complexity=TaskComplexity.MEDIUM,
                model_preference=ModelType.HYBRID,
                max_tokens=800
            )
            
            if not response or response.error:
                logger.warning(f"AI personalization failed for user {user_id}: {response.error if response else 'No response'}")
                return scored_items
                
            try:
                # Parse response (expected format is JSON array)
                ai_ranking = json.loads(response.content)
                if not isinstance(ai_ranking, list):
                    raise ValueError("Expected JSON array")
                    
                # Extract ID order from AI response
                ranked_ids = []
                for item in ai_ranking:
                    if isinstance(item, dict) and "id" in item:
                        ranked_ids.append(str(item["id"]))
                    elif isinstance(item, str):
                        ranked_ids.append(item)
                
                # Re-order top items based on AI ranking
                id_to_item = {str(item["id"]): item for item in top_items}
                ai_ranked_items = []
                
                for item_id in ranked_ids:
                    if item_id in id_to_item:
                        ai_ranked_items.append(id_to_item[item_id])
                
                # Add any missing items (fallback)
                for item in top_items:
                    if str(item["id"]) not in ranked_ids:
                        ai_ranked_items.append(item)
                
                # Combine AI-ranked top items with remaining items
                return ai_ranked_items + remaining_items
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse AI ranking response: {str(e)}")
                return scored_items
                
        except Exception as e:
            logger.error(f"Error in AI personalization for user {user_id}: {str(e)}", exc_info=True)
            return scored_items
    
    def _apply_diversity_and_exploration(
        self,
        user_id: int,
        scored_items: List[Dict[str, Any]],
        engagement_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply diversity and exploration adjustments to prevent filter bubbles
        and ensure variety in learning content.
        """
        if len(scored_items) <= 3:
            return scored_items
            
        result = []
        
        # Track seen content types and topics for diversity
        seen_content_types = set()
        seen_topics = set()
        
        # Exploration rate varies by engagement state
        exploration_rate = 0.2  # Default 20% exploration
        
        if engagement_state.get("state") == UserEngagementStateEnum.BORED:
            exploration_rate = 0.4  # More exploration for bored users
        elif engagement_state.get("state") == UserEngagementStateEnum.STRUGGLING:
            exploration_rate = 0.1  # Less exploration for struggling users
        
        # Apply diversity and exploration
        top_item_count = min(len(scored_items), 20)
        
        # Always include the top item
        if scored_items:
            top_item = scored_items[0]
            result.append(top_item)
            
            # Track its content type and topics
            seen_content_types.add(top_item.get("content_type", ""))
            for topic in top_item.get("metadata", {}).get("topics", []):
                seen_topics.add(topic)
        
        # Select remaining items with diversity and exploration
        remaining_pool = scored_items[1:top_item_count]
        
        # Implement exploration by occasionally selecting random items
        if np.random.random() < exploration_rate and len(scored_items) > top_item_count:
            exploration_items = scored_items[top_item_count:]
            if exploration_items:
                exploration_pick = np.random.choice(exploration_items)
                remaining_pool.append(exploration_pick)
        
        # Sort remaining pool by score
        remaining_pool.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Build final ranking with diversity
        while remaining_pool and len(result) < top_item_count:
            # First try to find diverse content type
            diverse_pick = None
            
            for item in remaining_pool:
                content_type = item.get("content_type", "")
                if content_type and content_type not in seen_content_types:
                    diverse_pick = item
                    break
            
            # If no diverse content type, try diverse topic
            if not diverse_pick:
                for item in remaining_pool:
                    item_topics = set(item.get("metadata", {}).get("topics", []))
                    if item_topics and not item_topics.issubset(seen_topics):
                        diverse_pick = item
                        break
            
            # If still no diverse pick, take the highest scored remaining item
            if not diverse_pick and remaining_pool:
                diverse_pick = remaining_pool[0]
            
            if diverse_pick:
                result.append(diverse_pick)
                remaining_pool.remove(diverse_pick)
                
                # Update seen content types and topics
                seen_content_types.add(diverse_pick.get("content_type", ""))
                for topic in diverse_pick.get("metadata", {}).get("topics", []):
                    seen_topics.add(topic)
        
        # Add any remaining items by score
        for item in scored_items:
            if item not in result:
                result.append(item)
                
        return result
    
    async def _log_ranking_event(
        self,
        user_id: int,
        ranked_items: List[Dict[str, Any]],
        processing_time: float,
        db: AsyncSession
    ):
        """Log ranking event for analysis and improvement."""
        try:
            # Create log entry for analytics
            log = AIConversationLog(
                user_id=user_id,
                session_id=f"feed_ranking_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                agent_type="feed_ranking",
                input_prompt=f"Feed ranking for user {user_id}",
                ai_response=json.dumps([
                    {"id": item.get("id"), "score": item.get("relevance_score")} 
                    for item in ranked_items[:10]
                ]),
                processed_response=f"Ranked {len(ranked_items)} items",
                model_used=AIModelTypeEnum.HYBRID,
                processing_time_ms=processing_time * 1000,
                error_occurred=False,
                timestamp=datetime.utcnow()
            )
            
            db.add(log)
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to log ranking event: {str(e)}")
            await db.rollback()


# Create singleton instance
feed_ranking_agent = FeedRankingAgent()
