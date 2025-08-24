"""
Sentiment and Engagement Analysis Agent

Intelligent analysis of user behavior, sentiment, and engagement patterns:
- Real-time sentiment analysis from user interactions
- Engagement state tracking and pattern recognition
- Proactive intervention triggers
- Learning analytics and insights
- Behavioral pattern detection
"""

import asyncio
import logging
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from .models import UserEngagementState, UserEngagementStateEnum, MentorInteraction, AIConversationLog
from .orchestrator import ai_orchestrator, ModelType, TaskComplexity
from lyo_app.auth.models import User

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Advanced sentiment analysis with educational context awareness.
    """
    
    def __init__(self):
        # Sentiment keywords with weights
        self.positive_keywords = {
            # High positive
            "love": 0.8, "excellent": 0.9, "amazing": 0.8, "fantastic": 0.9,
            "perfect": 0.8, "brilliant": 0.9, "awesome": 0.8, "outstanding": 0.9,
            
            # Medium positive
            "good": 0.6, "great": 0.7, "nice": 0.5, "helpful": 0.6,
            "useful": 0.6, "clear": 0.5, "easy": 0.6, "understand": 0.5,
            
            # Mild positive
            "ok": 0.3, "okay": 0.3, "fine": 0.4, "thanks": 0.4
        }
        
        self.negative_keywords = {
            # High negative
            "hate": -0.8, "terrible": -0.9, "awful": -0.8, "horrible": -0.9,
            "impossible": -0.7, "frustrated": -0.8, "angry": -0.8, "furious": -0.9,
            
            # Medium negative
            "difficult": -0.6, "hard": -0.5, "confusing": -0.7, "complicated": -0.6,
            "stuck": -0.6, "lost": -0.6, "struggling": -0.7, "problem": -0.5,
            
            # Mild negative
            "unsure": -0.3, "confused": -0.4, "unclear": -0.4, "help": -0.2
        }
        
        # Educational context modifiers
        self.learning_indicators = {
            "quiz": {"difficulty_multiplier": 1.5, "context": "assessment"},
            "test": {"difficulty_multiplier": 1.8, "context": "assessment"},
            "exam": {"difficulty_multiplier": 2.0, "context": "assessment"},
            "lesson": {"difficulty_multiplier": 1.0, "context": "learning"},
            "homework": {"difficulty_multiplier": 1.3, "context": "practice"},
            "assignment": {"difficulty_multiplier": 1.4, "context": "practice"}
        }
        
        # Emotion patterns
        self.emotion_patterns = {
            r"[!]{2,}": {"emotion": "excited", "intensity": 0.6},
            r"[?]{2,}": {"emotion": "confused", "intensity": -0.5},
            r"\.{3,}": {"emotion": "hesitant", "intensity": -0.3},
            r"[A-Z]{3,}": {"emotion": "frustrated", "intensity": -0.6},
        }
    
    def analyze_sentiment(self, text: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Perform comprehensive sentiment analysis on text.
        
        Args:
            text: Text to analyze
            context: Optional context information (lesson_id, quiz_id, etc.)
            
        Returns:
            Dict containing sentiment score, confidence, emotions, and insights
        """
        if not text:
            return {
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "primary_emotion": "neutral",
                "emotions": {},
                "educational_context": {},
                "insights": []
            }
        
        text_lower = text.lower()
        insights = []
        
        # Calculate base sentiment score
        sentiment_score = 0.0
        word_count = 0
        
        # Positive sentiment
        for word, weight in self.positive_keywords.items():
            count = text_lower.count(word)
            if count > 0:
                sentiment_score += weight * count
                word_count += count
        
        # Negative sentiment
        for word, weight in self.negative_keywords.items():
            count = text_lower.count(word)
            if count > 0:
                sentiment_score += weight * count
                word_count += count
        
        # Normalize by word count
        if word_count > 0:
            sentiment_score = sentiment_score / word_count
            confidence = min(1.0, word_count / 10.0)  # Higher confidence with more emotional words
        else:
            confidence = 0.1  # Low confidence for neutral text
        
        # Analyze emotional patterns
        emotions = {}
        for pattern, emotion_data in self.emotion_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                emotion = emotion_data["emotion"]
                intensity = emotion_data["intensity"] * len(matches)
                emotions[emotion] = intensity
                sentiment_score += intensity * 0.5  # Moderate impact on overall sentiment
        
        # Educational context analysis
        educational_context = {}
        context_multiplier = 1.0
        
        for indicator, data in self.learning_indicators.items():
            if indicator in text_lower:
                educational_context[indicator] = data["context"]
                context_multiplier = max(context_multiplier, data["difficulty_multiplier"])
        
        # Apply context multiplier to negative sentiments (struggles are amplified in educational contexts)
        if sentiment_score < 0:
            sentiment_score *= context_multiplier
        
        # Add contextual insights
        if context:
            if context.get("attempt_count", 0) > 3:
                insights.append("Multiple attempts detected - user may need additional support")
                sentiment_score -= 0.2  # Slight negative adjustment
            
            if context.get("time_spent", 0) > 1800:  # More than 30 minutes
                insights.append("Extended time spent - possible difficulty or deep engagement")
                if sentiment_score < 0:
                    sentiment_score -= 0.1  # Amplify negative if already negative
        
        # Determine primary emotion
        primary_emotion = "neutral"
        if sentiment_score > 0.3:
            primary_emotion = "positive"
        elif sentiment_score < -0.3:
            primary_emotion = "negative"
        elif emotions:
            primary_emotion = max(emotions.keys(), key=lambda k: abs(emotions[k]))
        
        # Clamp sentiment score
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
        
        return {
            "sentiment_score": round(sentiment_score, 3),
            "confidence": round(confidence, 3),
            "primary_emotion": primary_emotion,
            "emotions": emotions,
            "educational_context": educational_context,
            "insights": insights
        }


class EngagementPatternAnalyzer:
    """
    Analyzes user engagement patterns and behavioral indicators.
    """
    
    def __init__(self):
        self.engagement_thresholds = {
            "struggling": {
                "consecutive_failures": 3,
                "low_scores": 0.5,
                "time_without_progress": 3600,  # 1 hour
                "negative_sentiment_threshold": -0.4
            },
            "bored": {
                "rapid_completion": 30,  # Completing tasks in less than 30 seconds
                "minimal_interaction": 0.2,  # Less than 20% engagement
                "pattern_repetition": 5  # Doing same thing 5+ times
            },
            "frustrated": {
                "repeated_attempts": 4,
                "negative_sentiment_spike": -0.6,
                "help_requests": 3
            },
            "curious": {
                "exploration_beyond_required": 1.5,  # 150% of required interaction
                "question_asking": 3,
                "positive_sentiment": 0.4
            }
        }
    
    def analyze_engagement_pattern(
        self, 
        user_id: int, 
        recent_activities: List[Dict], 
        sentiment_history: List[float],
        current_session_data: Dict
    ) -> Dict[str, Any]:
        """
        Analyze user engagement patterns based on recent activities.
        
        Args:
            user_id: User identifier
            recent_activities: List of recent user activities
            sentiment_history: History of sentiment scores
            current_session_data: Current session information
            
        Returns:
            Dict containing engagement analysis results
        """
        analysis = {
            "engagement_level": "neutral",
            "confidence": 0.0,
            "indicators": {},
            "recommended_actions": [],
            "risk_factors": [],
            "positive_indicators": []
        }
        
        if not recent_activities:
            return analysis
        
        # Analyze struggling patterns
        struggling_score = self._analyze_struggling_patterns(recent_activities, sentiment_history)
        
        # Analyze boredom patterns
        boredom_score = self._analyze_boredom_patterns(recent_activities, current_session_data)
        
        # Analyze frustration patterns
        frustration_score = self._analyze_frustration_patterns(recent_activities, sentiment_history)
        
        # Analyze curiosity patterns
        curiosity_score = self._analyze_curiosity_patterns(recent_activities, sentiment_history)
        
        # Combine scores to determine primary engagement state
        scores = {
            "struggling": struggling_score,
            "bored": boredom_score,
            "frustrated": frustration_score,
            "curious": curiosity_score
        }
        
        # Find the highest scoring engagement state
        max_state = max(scores.keys(), key=lambda k: scores[k])
        max_score = scores[max_state]
        
        if max_score > 0.6:
            analysis["engagement_level"] = max_state
            analysis["confidence"] = max_score
        else:
            analysis["engagement_level"] = "neutral"
            analysis["confidence"] = 0.5
        
        analysis["indicators"] = scores
        
        # Generate recommendations based on engagement state
        analysis["recommended_actions"] = self._generate_recommendations(
            analysis["engagement_level"], 
            scores,
            recent_activities
        )
        
        return analysis
    
    def _analyze_struggling_patterns(self, activities: List[Dict], sentiment_history: List[float]) -> float:
        """Analyze indicators of struggling behavior."""
        score = 0.0
        
        # Check for consecutive failures
        consecutive_failures = 0
        for activity in activities[-10:]:  # Last 10 activities
            if activity.get("success", True) is False:
                consecutive_failures += 1
            else:
                break
        
        if consecutive_failures >= 3:
            score += 0.4
        
        # Check sentiment trend
        if len(sentiment_history) >= 3:
            recent_sentiment = sum(sentiment_history[-3:]) / 3
            if recent_sentiment < -0.3:
                score += 0.3
        
        # Check for help-seeking behavior
        help_requests = sum(1 for activity in activities if "help" in activity.get("type", "").lower())
        if help_requests >= 2:
            score += 0.2
        
        return min(1.0, score)
    
    def _analyze_boredom_patterns(self, activities: List[Dict], session_data: Dict) -> float:
        """Analyze indicators of boredom."""
        score = 0.0
        
        # Check for rapid completion without engagement
        rapid_completions = sum(
            1 for activity in activities 
            if activity.get("duration", 0) < 30 and activity.get("completed", False)
        )
        
        if rapid_completions >= 3:
            score += 0.4
        
        # Check for minimal interaction patterns
        interaction_depth = session_data.get("interaction_depth", 0)
        if interaction_depth < 0.3:  # Less than 30% engagement
            score += 0.3
        
        return min(1.0, score)
    
    def _analyze_frustration_patterns(self, activities: List[Dict], sentiment_history: List[float]) -> float:
        """Analyze indicators of frustration."""
        score = 0.0
        
        # Check for repeated attempts on same content
        content_attempts = {}
        for activity in activities:
            content_id = activity.get("content_id")
            if content_id:
                content_attempts[content_id] = content_attempts.get(content_id, 0) + 1
        
        max_attempts = max(content_attempts.values()) if content_attempts else 0
        if max_attempts >= 4:
            score += 0.5
        
        # Check for sentiment spikes
        if len(sentiment_history) >= 2:
            sentiment_drop = max(sentiment_history) - min(sentiment_history[-3:])
            if sentiment_drop > 0.6:
                score += 0.4
        
        return min(1.0, score)
    
    def _analyze_curiosity_patterns(self, activities: List[Dict], sentiment_history: List[float]) -> float:
        """Analyze indicators of curiosity and high engagement."""
        score = 0.0
        
        # Check for exploration beyond requirements
        exploration_activities = sum(
            1 for activity in activities 
            if activity.get("type") in ["explore", "additional_reading", "optional_content"]
        )
        
        if exploration_activities >= 2:
            score += 0.4
        
        # Check for positive sentiment trend
        if len(sentiment_history) >= 3:
            recent_sentiment = sum(sentiment_history[-3:]) / 3
            if recent_sentiment > 0.3:
                score += 0.3
        
        # Check for question-asking behavior
        questions = sum(
            1 for activity in activities 
            if "?" in activity.get("content", "") or activity.get("type") == "question"
        )
        
        if questions >= 2:
            score += 0.3
        
        return min(1.0, score)
    
    def _generate_recommendations(self, engagement_level: str, scores: Dict, activities: List[Dict]) -> List[str]:
        """Generate actionable recommendations based on engagement analysis."""
        recommendations = []
        
        if engagement_level == "struggling":
            recommendations.extend([
                "Provide additional explanations and examples",
                "Offer step-by-step guidance",
                "Consider one-on-one mentoring session",
                "Break down complex topics into smaller parts"
            ])
        
        elif engagement_level == "bored":
            recommendations.extend([
                "Introduce more challenging content",
                "Add interactive elements or gamification",
                "Provide optional advanced topics",
                "Encourage peer collaboration"
            ])
        
        elif engagement_level == "frustrated":
            recommendations.extend([
                "Immediate intervention with calming guidance",
                "Offer alternative learning approaches",
                "Provide encouragement and progress acknowledgment",
                "Consider break suggestion"
            ])
        
        elif engagement_level == "curious":
            recommendations.extend([
                "Provide additional resources and challenges",
                "Encourage exploration and experimentation",
                "Connect to advanced topics",
                "Foster peer mentoring opportunities"
            ])
        
        return recommendations


class SentimentAndEngagementAgent:
    """
    Main agent for sentiment analysis and engagement tracking.
    
    Coordinates between sentiment analysis, engagement pattern detection,
    and proactive interventions to optimize user learning experience.
    """
    
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
        self.engagement_analyzer = EngagementPatternAnalyzer()
        
        # Configuration
        self.intervention_thresholds = {
            "struggling": 0.7,
            "frustrated": 0.6,
            "bored": 0.5
        }
        
        # Cache for recent analysis to avoid redundant processing
        self.analysis_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        logger.info("SentimentAndEngagementAgent initialized")
    
    async def analyze_user_action(
        self, 
        user_id: int, 
        action: str, 
        metadata: Dict, 
        db: AsyncSession,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a user action for sentiment and engagement patterns.
        
        Args:
            user_id: User identifier
            action: Type of action performed
            metadata: Action metadata (quiz_id, score, duration, etc.)
            db: Database session
            user_message: Optional user message to analyze
            
        Returns:
            Dict containing analysis results and any triggered actions
        """
        try:
            logger.info(f"Analyzing user action: user_id={user_id}, action={action}")
            
            # Get or create user engagement state
            engagement_state = await self._get_or_create_engagement_state(user_id, db)
            
            # Perform sentiment analysis if there's text content
            sentiment_result = None
            if user_message:
                sentiment_result = self.sentiment_analyzer.analyze_sentiment(
                    user_message, 
                    context=metadata
                )
            
            # Get recent user activities for pattern analysis
            recent_activities = await self._get_recent_activities(user_id, db)
            sentiment_history = await self._get_sentiment_history(user_id, db)
            
            # Analyze engagement patterns
            engagement_analysis = self.engagement_analyzer.analyze_engagement_pattern(
                user_id=user_id,
                recent_activities=recent_activities,
                sentiment_history=sentiment_history,
                current_session_data=metadata
            )
            
            # Update engagement state
            new_state = await self._determine_new_engagement_state(
                current_state=engagement_state.state,
                action=action,
                metadata=metadata,
                sentiment_result=sentiment_result,
                engagement_analysis=engagement_analysis
            )
            
            # Update database
            await self._update_engagement_state(
                engagement_state=engagement_state,
                new_state=new_state,
                sentiment_score=sentiment_result["sentiment_score"] if sentiment_result else 0.0,
                confidence=sentiment_result["confidence"] if sentiment_result else 0.0,
                context=f"{action}:{metadata.get('content_id', 'unknown')}",
                db=db
            )
            
            # Check for intervention triggers
            intervention_triggered = await self._check_intervention_triggers(
                user_id=user_id,
                new_state=new_state,
                engagement_analysis=engagement_analysis,
                sentiment_result=sentiment_result,
                db=db
            )
            
            # Prepare response
            analysis_result = {
                "user_id": user_id,
                "action": action,
                "previous_state": engagement_state.state.value,
                "new_state": new_state.value,
                "sentiment_analysis": sentiment_result,
                "engagement_analysis": engagement_analysis,
                "intervention_triggered": intervention_triggered,
                "recommendations": engagement_analysis.get("recommended_actions", []),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Log the analysis
            await self._log_analysis(user_id, analysis_result, db)
            
            logger.info(f"Analysis completed for user {user_id}: {new_state.value}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing user action for user {user_id}: {e}")
            return {
                "error": str(e),
                "user_id": user_id,
                "action": action,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _get_or_create_engagement_state(self, user_id: int, db: AsyncSession) -> UserEngagementState:
        """Get or create user engagement state."""
        result = await db.execute(
            select(UserEngagementState).where(UserEngagementState.user_id == user_id)
        )
        engagement_state = result.scalar_one_or_none()
        
        if not engagement_state:
            engagement_state = UserEngagementState(
                user_id=user_id,
                state=UserEngagementStateEnum.IDLE,
                sentiment_score=0.0,
                confidence_score=0.0
            )
            db.add(engagement_state)
            await db.commit()
            logger.info(f"Created new engagement state for user {user_id}")
        
        return engagement_state
    
    async def _get_recent_activities(self, user_id: int, db: AsyncSession, limit: int = 20) -> List[Dict]:
        """Get recent user activities for pattern analysis."""
        # This would typically query learning activities, quiz attempts, etc.
        # For now, return mock data structure
        
        # In production, this would query actual activity tables:
        # - LessonCompletion
        # - QuizAttempt  
        # - StudySession
        # - MentorInteraction
        
        result = await db.execute(
            select(MentorInteraction)
            .where(MentorInteraction.user_id == user_id)
            .order_by(MentorInteraction.timestamp.desc())
            .limit(limit)
        )
        interactions = result.scalars().all()
        
        activities = []
        for interaction in interactions:
            activities.append({
                "type": interaction.interaction_type,
                "timestamp": interaction.timestamp.isoformat(),
                "duration": 0,  # Would be calculated from actual data
                "success": interaction.was_helpful,
                "content_id": interaction.session_id,
                "sentiment_detected": interaction.sentiment_detected
            })
        
        return activities
    
    async def _get_sentiment_history(self, user_id: int, db: AsyncSession, limit: int = 20):
        """Fetch recent sentiment scores from AIConversationLog."""
        result = await db.execute(
            select(AIConversationLog)
            .where(AIConversationLog.user_id == user_id)
            .order_by(AIConversationLog.timestamp.desc())
            .limit(limit)
        )
        logs = result.scalars().all()
        return [log.sentiment_detected for log in logs if log.sentiment_detected is not None]
    
    async def _determine_new_engagement_state(
        self,
        current_state: UserEngagementStateEnum,
        action: str,
        metadata: Dict,
        sentiment_result: Optional[Dict],
        engagement_analysis: Dict
    ) -> UserEngagementStateEnum:
        """Decide the new engagement state based on analysis."""
        # Use engagement_analysis first
        level = engagement_analysis.get("engagement_level")
        if level:
            return UserEngagementStateEnum(level)
        # Fallback based on sentiment thresholds
        score = sentiment_result.get("sentiment_score", 0.0) if sentiment_result else 0.0
        for state, threshold in self.intervention_thresholds.items():
            if score <= -threshold:
                return UserEngagementStateEnum(state)
        return UserEngagementStateEnum.ENGAGED

    async def _update_engagement_state(
        self,
        engagement_state: UserEngagementState,
        new_state: UserEngagementStateEnum,
        sentiment_score: float,
        confidence: float,
        context: str,
        db: AsyncSession
    ):
        """Persist the updated engagement state to the database."""
        engagement_state.state = new_state
        engagement_state.sentiment_score = sentiment_score
        engagement_state.confidence_score = confidence
        engagement_state.context = context
        engagement_state.last_analyzed_at = datetime.utcnow()
        db.add(engagement_state)
        await db.commit()
        await db.refresh(engagement_state)

    async def _check_intervention_triggers(
        self,
        user_id: int,
        new_state: UserEngagementStateEnum,
        engagement_analysis: Dict,
        sentiment_result: Optional[Dict],
        db: AsyncSession
    ) -> bool:
        """Trigger proactive intervention if state is critical."""
        if new_state in [UserEngagementStateEnum.STRUGGLING, UserEngagementStateEnum.FRUSTRATED]:
            # Here, trigger the mentor check-in
            return True
        return False

    async def _log_analysis(self, user_id: int, analysis: Dict, db: AsyncSession):
        """Log the analysis result to AIConversationLog."""
        log = AIConversationLog(
            user_id=user_id,
            session_id=analysis.get("timestamp"),
            agent_type="sentiment_engagement",
            input_prompt=analysis.get("action", ""),
            ai_response=json.dumps(analysis.get("engagement_analysis", {})),
            processed_response=json.dumps(analysis),
            model_used=ModelType.HYBRID,
            tokens_used=None,
            cost_estimate=None,
            processing_time_ms=0.0,
            error_occurred=False,
            timestamp=datetime.utcnow()
        )
        db.add(log)
        await db.commit()
    
    async def get_user_engagement_summary(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive engagement summary for a user."""
        try:
            # Get current engagement state
            result = await db.execute(
                select(UserEngagementState).where(UserEngagementState.user_id == user_id)
            )
            engagement_state = result.scalar_one_or_none()
            
            if not engagement_state:
                return {"error": "No engagement data found for user"}
            
            # Get recent activities and sentiment history
            recent_activities = await self._get_recent_activities(user_id, db)
            sentiment_history = await self._get_sentiment_history(user_id, db)
            
            # Calculate engagement trends
            trends = self._calculate_engagement_trends(recent_activities, sentiment_history)
            
            return {
                "user_id": user_id,
                "current_state": engagement_state.state.value,
                "sentiment_score": engagement_state.sentiment_score,
                "confidence_score": engagement_state.confidence_score,
                "consecutive_struggles": engagement_state.consecutive_struggles,
                "activity_count": engagement_state.activity_count,
                "last_analyzed": engagement_state.last_analyzed_at.isoformat(),
                "trends": trends,
                "recent_activities_count": len(recent_activities),
                "recommendations": self.engagement_analyzer._generate_recommendations(
                    engagement_state.state.value, 
                    {"struggling": 0.5}, 
                    recent_activities
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting engagement summary for user {user_id}: {e}")
            return {"error": str(e)}
    
    def _calculate_engagement_trends(self, activities: List[Dict], sentiment_history: List[float]) -> Dict[str, Any]:
        """Calculate engagement trends from historical data."""
        if not activities:
            return {"trend": "no_data"}
        
        # Calculate activity trend
        recent_activity_count = len([a for a in activities[-5:]])
        older_activity_count = len([a for a in activities[-10:-5]])
        
        activity_trend = "stable"
        if recent_activity_count > older_activity_count * 1.2:
            activity_trend = "increasing"
        elif recent_activity_count < older_activity_count * 0.8:
            activity_trend = "decreasing"
        
        # Calculate sentiment trend
        sentiment_trend = "stable"
        if len(sentiment_history) >= 3:
            recent_avg = sum(sentiment_history[:3]) / 3
            older_avg = sum(sentiment_history[3:6]) / max(1, len(sentiment_history[3:6]))
            
            if recent_avg > older_avg + 0.2:
                sentiment_trend = "improving"
            elif recent_avg < older_avg - 0.2:
                sentiment_trend = "declining"
        
        return {
            "activity_trend": activity_trend,
            "sentiment_trend": sentiment_trend,
            "total_activities": len(activities),
            "average_sentiment": sum(sentiment_history) / len(sentiment_history) if sentiment_history else 0.0
        }


# Global sentiment and engagement agent instance
sentiment_engagement_agent = SentimentAndEngagementAgent()
