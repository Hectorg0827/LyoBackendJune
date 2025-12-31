"""
Dropout Prevention System

Identifies users at risk of churning and creates personalized re-engagement strategies.
Early intervention can save 60%+ of at-risk users.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
import statistics
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from .models import DropoutRiskScore, LearningPlateau, SkillRegression
from lyo_app.personalization.models import LearnerState, LearnerMastery
from lyo_app.gamification.models import Streak
from lyo_app.learning.models import LessonCompletion, CourseEnrollment

logger = logging.getLogger(__name__)


class DropoutPredictor:
    """
    Predicts churn risk and generates personalized re-engagement strategies.
    """

    def __init__(self):
        # Risk thresholds
        self.RISK_THRESHOLDS = {
            'low': 0.3,
            'medium': 0.5,
            'high': 0.7,
            'critical': 0.85
        }

    async def calculate_churn_risk(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Tuple[float, str, List[str]]:
        """
        Calculate churn risk score and identify risk factors.

        Returns:
            (risk_score, risk_level, risk_factors)
        """
        metrics = await self._get_user_metrics(user_id, db)

        risk_score = 0.0
        risk_factors = []

        # Factor 1: Session frequency declining (25% weight)
        if metrics['session_frequency_trend'] < -0.3:
            risk_score += 0.25
            risk_factors.append("declining_engagement")

        # Factor 2: Increasing gaps between sessions (20% weight)
        if metrics['avg_days_between_sessions'] > 3:
            risk_score += 0.20
            risk_factors.append("infrequent_sessions")

        # Factor 3: Negative sentiment trend (20% weight)
        if metrics['sentiment_trend_7d'] < -0.3:
            risk_score += 0.20
            risk_factors.append("negative_sentiment")

        # Factor 4: No recent progress (15% weight)
        if metrics['days_since_last_completion'] > 7:
            risk_score += 0.15
            risk_factors.append("no_recent_progress")

        # Factor 5: Declining performance (10% weight)
        if metrics['performance_trend'] < -0.2:
            risk_score += 0.10
            risk_factors.append("declining_performance")

        # Factor 6: Broken streak (10% weight)
        if metrics['longest_streak'] > 7 and metrics['current_streak'] == 0:
            risk_score += 0.10
            risk_factors.append("broken_streak")

        risk_score = min(risk_score, 1.0)

        # Determine risk level
        risk_level = self._get_risk_level(risk_score)

        # Store risk score
        await self._store_risk_score(user_id, risk_score, risk_level, risk_factors, metrics, db)

        return risk_score, risk_level, risk_factors

    def _get_risk_level(self, risk_score: float) -> str:
        """Convert numerical risk score to categorical level."""
        if risk_score >= self.RISK_THRESHOLDS['critical']:
            return 'critical'
        elif risk_score >= self.RISK_THRESHOLDS['high']:
            return 'high'
        elif risk_score >= self.RISK_THRESHOLDS['medium']:
            return 'medium'
        else:
            return 'low'

    async def _get_user_metrics(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Gather all metrics needed for churn prediction."""
        metrics = {}

        # Session frequency trend
        metrics['session_frequency_trend'] = await self._calculate_session_frequency_trend(
            user_id, db
        )

        # Average days between sessions
        metrics['avg_days_between_sessions'] = await self._calculate_avg_days_between_sessions(
            user_id, db
        )

        # Sentiment trend (7 days)
        metrics['sentiment_trend_7d'] = await self._calculate_sentiment_trend(
            user_id, db, days=7
        )

        # Days since last completion
        metrics['days_since_last_completion'] = await self._days_since_last_completion(
            user_id, db
        )

        # Performance trend
        metrics['performance_trend'] = await self._calculate_performance_trend(
            user_id, db
        )

        # Streak info
        streak_info = await self._get_streak_info(user_id, db)
        metrics['longest_streak'] = streak_info['longest']
        metrics['current_streak'] = streak_info['current']

        return metrics

    async def _calculate_session_frequency_trend(
        self,
        user_id: int,
        db: AsyncSession
    ) -> float:
        """
        Calculate trend in session frequency (sessions per week).
        Negative = declining, Positive = increasing.
        """
        # Get sessions for last 4 weeks
        four_weeks_ago = datetime.utcnow() - timedelta(days=28)

        stmt = select(
            func.date_trunc('week', LessonCompletion.completed_at).label('week'),
            func.count(func.distinct(func.date(LessonCompletion.completed_at))).label('days')
        ).where(
            and_(
                LessonCompletion.user_id == user_id,
                LessonCompletion.completed_at >= four_weeks_ago
            )
        ).group_by('week').order_by('week')

        result = await db.execute(stmt)
        weekly_sessions = [row[1] for row in result.all()]

        if len(weekly_sessions) < 2:
            return 0.0  # Not enough data

        # Calculate trend (simple linear regression slope)
        weeks = list(range(len(weekly_sessions)))
        if len(weeks) > 1:
            # Manual linear regression: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
            mean_x = statistics.mean(weeks)
            mean_y = statistics.mean(weekly_sessions)
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(weeks, weekly_sessions))
            denominator = sum((x - mean_x) ** 2 for x in weeks)
            slope = numerator / denominator if denominator != 0 else 0.0
            # Normalize: divide by mean to get percentage change
            return slope / mean_y if mean_y > 0 else 0.0

        return 0.0

    async def _calculate_avg_days_between_sessions(
        self,
        user_id: int,
        db: AsyncSession
    ) -> float:
        """Calculate average number of days between learning sessions."""
        # Get last 10 session dates
        stmt = select(func.date(LessonCompletion.completed_at).label('session_date')).where(
            LessonCompletion.user_id == user_id
        ).group_by('session_date').order_by(desc('session_date')).limit(10)

        result = await db.execute(stmt)
        session_dates = [row[0] for row in result.all()]

        if len(session_dates) < 2:
            return 0.0

        # Calculate gaps
        gaps = []
        for i in range(len(session_dates) - 1):
            gap = (session_dates[i] - session_dates[i+1]).days
            gaps.append(gap)

        return statistics.mean(gaps) if gaps else 0.0

    async def _calculate_sentiment_trend(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 7
    ) -> float:
        """Calculate sentiment trend over recent days."""
        # Placeholder - integrate with your sentiment tracking
        # Return value between -1 (getting worse) and 1 (getting better)
        return 0.0

    async def _days_since_last_completion(
        self,
        user_id: int,
        db: AsyncSession
    ) -> int:
        """Days since user last completed any lesson."""
        stmt = select(func.max(LessonCompletion.completed_at)).where(
            LessonCompletion.user_id == user_id
        )
        result = await db.execute(stmt)
        last_completion = result.scalar()

        if last_completion:
            return (datetime.utcnow() - last_completion).days

        return 999

    async def _calculate_performance_trend(
        self,
        user_id: int,
        db: AsyncSession
    ) -> float:
        """
        Calculate trend in performance (mastery levels).
        Negative = declining, Positive = improving.
        """
        # Get recent mastery updates (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        stmt = select(LearnerMastery).where(
            and_(
                LearnerMastery.user_id == user_id,
                LearnerMastery.last_seen >= thirty_days_ago
            )
        ).order_by(LearnerMastery.last_seen)

        result = await db.execute(stmt)
        masteries = result.scalars().all()

        if len(masteries) < 2:
            return 0.0

        # Calculate trend in mastery levels
        mastery_levels = [m.mastery_level for m in masteries]
        time_points = list(range(len(mastery_levels)))

        if len(time_points) > 1:
            # Manual linear regression
            mean_x = statistics.mean(time_points)
            mean_y = statistics.mean(mastery_levels)
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(time_points, mastery_levels))
            denominator = sum((x - mean_x) ** 2 for x in time_points)
            slope = numerator / denominator if denominator != 0 else 0.0
            return slope

        return 0.0

    async def _get_streak_info(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, int]:
        """Get user's streak information."""
        stmt = select(Streak).where(
            and_(
                Streak.user_id == user_id,
                Streak.streak_type == "daily_login"
            )
        )
        result = await db.execute(stmt)
        streak = result.scalar_one_or_none()

        if streak:
            return {
                'current': streak.current_count,
                'longest': streak.max_count
            }

        return {'current': 0, 'longest': 0}

    async def _store_risk_score(
        self,
        user_id: int,
        risk_score: float,
        risk_level: str,
        risk_factors: List[str],
        metrics: Dict[str, Any],
        db: AsyncSession
    ):
        """Store or update dropout risk score."""
        stmt = select(DropoutRiskScore).where(DropoutRiskScore.user_id == user_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.risk_score = risk_score
            existing.risk_level = risk_level
            existing.risk_factors = risk_factors
            existing.session_frequency_trend = metrics['session_frequency_trend']
            existing.avg_days_between_sessions = metrics['avg_days_between_sessions']
            existing.sentiment_trend_7d = metrics['sentiment_trend_7d']
            existing.days_since_last_completion = metrics['days_since_last_completion']
            existing.performance_trend = metrics['performance_trend']
            existing.longest_streak = metrics['longest_streak']
            existing.current_streak = metrics['current_streak']
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            risk = DropoutRiskScore(
                user_id=user_id,
                risk_score=risk_score,
                risk_level=risk_level,
                risk_factors=risk_factors,
                session_frequency_trend=metrics['session_frequency_trend'],
                avg_days_between_sessions=metrics['avg_days_between_sessions'],
                sentiment_trend_7d=metrics['sentiment_trend_7d'],
                days_since_last_completion=metrics['days_since_last_completion'],
                performance_trend=metrics['performance_trend'],
                longest_streak=metrics['longest_streak'],
                current_streak=metrics['current_streak']
            )
            db.add(risk)

        await db.commit()

    async def generate_reengagement_strategy(
        self,
        user_id: int,
        risk_score: float,
        risk_factors: List[str],
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Generate personalized re-engagement strategy based on risk factors.
        """
        if risk_score < 0.3:
            return None  # Low risk, no intervention needed

        strategy = {
            "urgency": "critical" if risk_score > 0.7 else "high" if risk_score > 0.5 else "medium",
            "interventions": []
        }

        # Tailor interventions to specific risk factors
        if "declining_engagement" in risk_factors:
            strategy["interventions"].append({
                "type": "personal_check_in",
                "priority": 9,
                "title": "We miss you!",
                "message": "I noticed you haven't been around as much. What's been going on?",
                "action": "open_chat_for_checkin"
            })

        if "negative_sentiment" in risk_factors:
            strategy["interventions"].append({
                "type": "difficulty_adjustment",
                "priority": 8,
                "title": "Let's make this easier",
                "message": "Things seemed tough lately. Want to try something more approachable?",
                "action": "suggest_easier_content"
            })

        if "no_recent_progress" in risk_factors:
            strategy["interventions"].append({
                "type": "quick_win",
                "priority": 7,
                "title": "Let's get a quick win!",
                "message": "This 5-minute lesson is perfect for you. Build some momentum?",
                "action": "recommend_easy_lesson"
            })

        if "broken_streak" in risk_factors:
            strategy["interventions"].append({
                "type": "streak_restart",
                "priority": 6,
                "title": "Start fresh",
                "message": "Ready to start a new streak? You had an amazing run before!",
                "action": "restart_streak_challenge"
            })

        if "infrequent_sessions" in risk_factors:
            strategy["interventions"].append({
                "type": "scheduling_help",
                "priority": 5,
                "title": "Let's make time",
                "message": "Want me to help you schedule regular study time?",
                "action": "open_schedule_planner"
            })

        if "declining_performance" in risk_factors:
            strategy["interventions"].append({
                "type": "review_fundamentals",
                "priority": 6,
                "title": "Back to basics",
                "message": "Let's strengthen your foundation with a quick review.",
                "action": "start_fundamentals_review"
            })

        # Store strategy
        await self._store_strategy(user_id, strategy, db)

        return strategy

    async def _store_strategy(
        self,
        user_id: int,
        strategy: Dict[str, Any],
        db: AsyncSession
    ):
        """Store re-engagement strategy."""
        stmt = select(DropoutRiskScore).where(DropoutRiskScore.user_id == user_id)
        result = await db.execute(stmt)
        risk = result.scalar_one_or_none()

        if risk:
            risk.reengagement_strategy = strategy
            await db.commit()

    async def mark_strategy_executed(
        self,
        user_id: int,
        db: AsyncSession
    ):
        """Mark that re-engagement strategy was executed."""
        stmt = select(DropoutRiskScore).where(DropoutRiskScore.user_id == user_id)
        result = await db.execute(stmt)
        risk = result.scalar_one_or_none()

        if risk:
            risk.strategy_executed = True
            risk.strategy_executed_at = datetime.utcnow()
            await db.commit()

    async def record_user_return(
        self,
        user_id: int,
        db: AsyncSession
    ):
        """
        Record that user returned after being at risk.
        Used for measuring re-engagement effectiveness.
        """
        stmt = select(DropoutRiskScore).where(DropoutRiskScore.user_id == user_id)
        result = await db.execute(stmt)
        risk = result.scalar_one_or_none()

        if risk and risk.risk_score > 0.5:  # Was at risk
            risk.user_returned = True
            risk.returned_at = datetime.utcnow()
            await db.commit()

            logger.info(
                f"User {user_id} returned after risk level {risk.risk_level}. "
                f"Strategy: {risk.reengagement_strategy is not None}"
            )


# Global singleton
dropout_predictor = DropoutPredictor()
