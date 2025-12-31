"""
Struggle Predictor

Predicts when a user will struggle with content BEFORE they attempt it.
Uses ML-inspired features with rule-based decision making (MVP).
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from .models import StrugglePrediction
from lyo_app.personalization.models import LearnerMastery, LearnerState
from lyo_app.learning.models import LessonCompletion

logger = logging.getLogger(__name__)


class StrugglePredictor:
    """
    Predicts probability that a user will struggle with content.

    Features:
    - Prerequisite mastery
    - Similar content performance
    - Content difficulty
    - Time since last review
    - Current cognitive load
    - Sentiment trends
    """

    def __init__(self):
        # Feature weights (can be tuned)
        self.weights = {
            'prereq_mastery': 0.35,
            'similar_performance': 0.25,
            'content_difficulty': 0.20,
            'recency': 0.10,
            'cognitive_load': 0.05,
            'sentiment': 0.05
        }

        # Thresholds
        self.STRUGGLE_THRESHOLD = 0.6  # >0.6 = likely to struggle
        self.HIGH_CONFIDENCE_THRESHOLD = 0.7  # >0.7 = high confidence

    async def predict_struggle(
        self,
        user_id: int,
        content_id: str,
        content_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Predict struggle probability for user attempting this content.

        Returns:
            (struggle_probability, confidence, features_dict)
        """
        # Extract features
        features = await self._extract_features(
            user_id,
            content_id,
            content_metadata,
            db
        )

        # Calculate struggle probability
        struggle_prob = self._calculate_struggle_probability(features)

        # Calculate confidence based on data availability
        confidence = self._calculate_confidence(features)

        # Store prediction
        await self._store_prediction(
            user_id,
            content_id,
            content_metadata.get('type', 'lesson'),
            struggle_prob,
            confidence,
            features,
            db
        )

        return struggle_prob, confidence, features

    async def _extract_features(
        self,
        user_id: int,
        content_id: str,
        content_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, float]:
        """Extract all features for prediction."""

        features = {}

        # 1. Prerequisite mastery
        prerequisites = content_metadata.get('prerequisites', [])
        if prerequisites:
            features['prereq_mastery'] = await self._get_average_mastery(
                user_id, prerequisites, db
            )
        else:
            features['prereq_mastery'] = 0.5  # Neutral if no prereqs

        # 2. Similar content performance
        similar_topics = content_metadata.get('similar_topics', [])
        if similar_topics:
            features['similar_performance'] = await self._get_similar_content_performance(
                user_id, similar_topics, db
            )
        else:
            features['similar_performance'] = 0.5  # Neutral

        # 3. Content difficulty (absolute)
        features['content_difficulty'] = content_metadata.get('difficulty_rating', 0.5)

        # 4. Recency of related concepts
        if prerequisites:
            days_since = await self._days_since_last_review(user_id, prerequisites, db)
            # Normalize: 0 days = 0.0 (good), 30+ days = 1.0 (bad)
            features['recency'] = min(days_since / 30.0, 1.0)
        else:
            features['recency'] = 0.5

        # 5. Current cognitive load
        recent_session = await self._get_recent_session_stats(user_id, db)
        features['cognitive_load'] = recent_session.get('difficulty_score', 0.5)

        # 6. Sentiment trend
        sentiment = await self._get_sentiment_trend(user_id, db, days=3)
        # Convert from [-1, 1] to [0, 1], then invert (negative sentiment = higher struggle risk)
        features['sentiment'] = (1 - (sentiment + 1) / 2)

        return features

    def _calculate_struggle_probability(self, features: Dict[str, float]) -> float:
        """
        Calculate struggle probability using weighted features.

        High struggle if:
        - Low prerequisite mastery
        - Poor performance on similar content
        - High content difficulty
        - Long time since review
        - High cognitive load
        - Negative sentiment
        """
        struggle_score = 0.0

        # Each feature contributes to struggle probability
        struggle_score += (1 - features['prereq_mastery']) * self.weights['prereq_mastery']
        struggle_score += (1 - features['similar_performance']) * self.weights['similar_performance']
        struggle_score += features['content_difficulty'] * self.weights['content_difficulty']
        struggle_score += features['recency'] * self.weights['recency']
        struggle_score += features['cognitive_load'] * self.weights['cognitive_load']
        struggle_score += features['sentiment'] * self.weights['sentiment']

        return min(max(struggle_score, 0.0), 1.0)

    def _calculate_confidence(self, features: Dict[str, float]) -> float:
        """
        Calculate confidence in prediction based on data availability.

        High confidence if we have:
        - Known prerequisite mastery
        - Similar content history
        - Recent activity
        """
        confidence = 0.0

        # Check data availability
        if features['prereq_mastery'] != 0.5:  # We have real prereq data
            confidence += 0.4
        if features['similar_performance'] != 0.5:  # We have similar content data
            confidence += 0.3
        if features['recency'] < 0.5:  # Recent practice
            confidence += 0.2
        if features['cognitive_load'] != 0.5:  # We have recent session data
            confidence += 0.1

        return min(confidence, 1.0)

    async def _get_average_mastery(
        self,
        user_id: int,
        skill_ids: list,
        db: AsyncSession
    ) -> float:
        """Get average mastery across prerequisite skills."""
        stmt = select(func.avg(LearnerMastery.mastery_level)).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.skill_id.in_(skill_ids)
            )
        )
        result = await db.execute(stmt)
        avg_mastery = result.scalar()

        return avg_mastery if avg_mastery is not None else 0.0

    async def _get_similar_content_performance(
        self,
        user_id: int,
        similar_topics: list,
        db: AsyncSession
    ) -> float:
        """Get average performance on similar content."""
        # Get masteries for similar topics
        stmt = select(func.avg(LearnerMastery.mastery_level)).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.skill_id.in_(similar_topics)
            )
        )
        result = await db.execute(stmt)
        avg_performance = result.scalar()

        return avg_performance if avg_performance is not None else 0.5

    async def _days_since_last_review(
        self,
        user_id: int,
        skill_ids: list,
        db: AsyncSession
    ) -> int:
        """Get days since last reviewed any of these skills."""
        stmt = select(func.max(LearnerMastery.last_seen)).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.skill_id.in_(skill_ids)
            )
        )
        result = await db.execute(stmt)
        last_seen = result.scalar()

        if last_seen:
            return (datetime.utcnow() - last_seen).days
        return 999  # Never practiced

    async def _get_recent_session_stats(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, float]:
        """Get stats from recent learning session."""
        # Get last 5 lesson completions
        stmt = select(LessonCompletion).where(
            LessonCompletion.user_id == user_id
        ).order_by(LessonCompletion.completed_at.desc()).limit(5)

        result = await db.execute(stmt)
        completions = result.scalars().all()

        if not completions:
            return {'difficulty_score': 0.5}

        # Calculate average difficulty of recent sessions
        # (you might have a difficulty field on completions, or infer from time taken)
        return {'difficulty_score': 0.5}  # Placeholder

    async def _get_sentiment_trend(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 3
    ) -> float:
        """
        Get sentiment trend over recent days.
        Returns value between -1 (negative) and 1 (positive).
        """
        # Query learner state or sentiment tracking
        stmt = select(LearnerState).where(LearnerState.user_id == user_id)
        result = await db.execute(stmt)
        state = result.scalar_one_or_none()

        if state and hasattr(state, 'current_mood'):
            # Return normalized sentiment
            return 0.0  # Placeholder - implement based on your sentiment tracking

        return 0.0  # Neutral

    async def _store_prediction(
        self,
        user_id: int,
        content_id: str,
        content_type: str,
        struggle_probability: float,
        confidence: float,
        features: Dict[str, float],
        db: AsyncSession
    ):
        """Store prediction for future analysis."""
        prediction = StrugglePrediction(
            user_id=user_id,
            content_id=content_id,
            content_type=content_type,
            struggle_probability=struggle_probability,
            confidence=confidence,
            prereq_mastery=features.get('prereq_mastery'),
            similar_performance=features.get('similar_performance'),
            content_difficulty=features.get('content_difficulty'),
            days_since_review=int(features.get('recency', 0) * 30),
            cognitive_load=features.get('cognitive_load'),
            sentiment_trend=features.get('sentiment'),
            prediction_features=features
        )

        db.add(prediction)
        await db.commit()

    async def should_offer_preemptive_help(
        self,
        user_id: int,
        content_id: str,
        content_metadata: Dict[str, Any],
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if we should offer help BEFORE user starts content.

        Returns:
            (should_offer, help_message)
        """
        struggle_prob, confidence, features = await self.predict_struggle(
            user_id,
            content_id,
            content_metadata,
            db
        )

        # Only offer help if:
        # 1. High struggle probability (>0.6)
        # 2. High confidence in prediction (>0.7)
        if struggle_prob > self.STRUGGLE_THRESHOLD and confidence > self.HIGH_CONFIDENCE_THRESHOLD:
            # Generate contextual help message
            message = await self._generate_help_message(struggle_prob, features, content_metadata)
            return True, message

        return False, None

    async def _generate_help_message(
        self,
        struggle_prob: float,
        features: Dict[str, float],
        content_metadata: Dict[str, Any]
    ) -> str:
        """Generate contextual help message based on why user might struggle."""

        # Identify primary struggle factor
        if features.get('prereq_mastery', 1.0) < 0.4:
            return "This builds on concepts you haven't fully mastered. Want to review the basics first?"

        elif features.get('recency', 0.0) > 0.6:
            return "It's been a while since you reviewed related topics. Quick refresher?"

        elif features.get('content_difficulty', 0.5) > 0.7:
            return "This is a challenging topic. Want me to break it down step-by-step?"

        elif features.get('cognitive_load', 0.5) > 0.7:
            return "You've been working hard. Want to try something easier first?"

        else:
            return "This might be tricky. Want a walkthrough before you start?"

    async def record_actual_outcome(
        self,
        user_id: int,
        content_id: str,
        struggled: bool,
        db: AsyncSession
    ):
        """
        Record actual outcome for improving predictions.
        Called after user completes content.
        """
        # Find most recent prediction for this content
        stmt = select(StrugglePrediction).where(
            and_(
                StrugglePrediction.user_id == user_id,
                StrugglePrediction.content_id == content_id,
                StrugglePrediction.actual_struggled == None
            )
        ).order_by(StrugglePrediction.predicted_at.desc()).limit(1)

        result = await db.execute(stmt)
        prediction = result.scalar_one_or_none()

        if prediction:
            prediction.actual_struggled = struggled
            prediction.actual_outcome_at = datetime.utcnow()
            await db.commit()

            # Log prediction accuracy for monitoring
            was_correct = (
                (prediction.struggle_probability > 0.5 and struggled) or
                (prediction.struggle_probability <= 0.5 and not struggled)
            )
            logger.info(
                f"Struggle prediction for user {user_id}, content {content_id}: "
                f"predicted={prediction.struggle_probability:.2f}, "
                f"actual={'struggled' if struggled else 'succeeded'}, "
                f"correct={was_correct}"
            )


# Global singleton
struggle_predictor = StrugglePredictor()
