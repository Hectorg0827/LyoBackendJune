"""
Optimal Timing System

Learns user's peak learning times and schedules interventions for maximum impact.
Personalizes notification timing based on historical performance patterns.
"""

import logging
from datetime import datetime, time, timedelta
from typing import Dict, Any, List, Optional, Tuple
import statistics
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from .models import UserTimingProfile
from lyo_app.learning.models import LessonCompletion
from lyo_app.personalization.models import LearnerMastery

logger = logging.getLogger(__name__)


class TimingOptimizer:
    """
    Learns optimal times for each user and schedules interventions accordingly.
    """

    def __init__(self):
        self.MIN_SESSIONS_FOR_CONFIDENCE = 10  # Need at least 10 sessions for patterns
        self.PERFORMANCE_THRESHOLD = 0.7  # Consider hour "peak" if avg performance >0.7

    async def analyze_user_timing(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyze user's learning patterns and identify optimal times.

        Returns timing profile with:
        - Peak learning hours
        - Best days of week
        - Optimal session length
        - Performance by time of day
        """
        # Get session history
        sessions = await self._get_session_history(user_id, db)

        if len(sessions) < self.MIN_SESSIONS_FOR_CONFIDENCE:
            return self._get_default_profile()

        profile = {}

        # Analyze performance by hour of day
        profile['performance_by_hour'] = self._analyze_performance_by_hour(sessions)

        # Identify peak hours
        profile['peak_hours'] = self._identify_peak_hours(profile['performance_by_hour'])

        # Optimal study time (most consistent peak hour)
        profile['optimal_study_time'] = self._determine_optimal_study_time(profile['peak_hours'])

        # Analyze by day of week
        profile['performance_by_day'] = self._analyze_performance_by_day(sessions)
        profile['best_days'] = self._identify_best_days(profile['performance_by_day'])

        # Session duration patterns
        profile['avg_session_duration'] = self._calculate_avg_session_duration(sessions)
        profile['preferred_session_length'] = self._infer_preferred_session_length(sessions)

        # Activity patterns
        profile['most_active_hour'] = self._find_most_active_hour(sessions)
        profile['least_active_hour'] = self._find_least_active_hour(sessions)

        # Study day patterns
        profile['typical_study_days'] = self._identify_typical_study_days(sessions)

        # Calculate confidence
        profile['sessions_analyzed'] = len(sessions)
        profile['confidence'] = self._calculate_confidence(len(sessions))

        # Store profile
        await self._store_timing_profile(user_id, profile, db)

        return profile

    async def _get_session_history(
        self,
        user_id: int,
        db: AsyncSession,
        days: int = 90
    ) -> List[Dict[str, Any]]:
        """Get user's learning sessions with performance metrics."""
        since = datetime.utcnow() - timedelta(days=days)

        # Get lesson completions
        stmt = select(LessonCompletion).where(
            and_(
                LessonCompletion.user_id == user_id,
                LessonCompletion.completed_at >= since
            )
        ).order_by(LessonCompletion.completed_at)

        result = await db.execute(stmt)
        completions = result.scalars().all()

        sessions = []
        for completion in completions:
            # Infer performance (you might have actual scores)
            performance = self._infer_performance(completion)

            sessions.append({
                'datetime': completion.completed_at,
                'hour': completion.completed_at.hour,
                'day_of_week': completion.completed_at.weekday(),  # 0=Monday
                'performance': performance,
                'duration_minutes': getattr(completion, 'duration_minutes', 30)  # Default
            })

        return sessions

    def _infer_performance(self, completion) -> float:
        """Infer performance score from completion data."""
        # If you have actual scores, use them
        # Otherwise, infer from available data
        if hasattr(completion, 'score') and completion.score is not None:
            return completion.score / 100.0  # Normalize to 0-1

        # Placeholder: assume successful completion = 0.75
        return 0.75

    def _analyze_performance_by_hour(
        self,
        sessions: List[Dict[str, Any]]
    ) -> Dict[int, float]:
        """Calculate average performance for each hour of day."""
        performance_by_hour = {}

        for hour in range(24):
            hour_sessions = [s for s in sessions if s['hour'] == hour]
            if hour_sessions:
                avg_performance = statistics.mean([s['performance'] for s in hour_sessions])
                performance_by_hour[hour] = float(avg_performance)

        return performance_by_hour

    def _identify_peak_hours(
        self,
        performance_by_hour: Dict[int, float]
    ) -> List[int]:
        """Identify hours when user performs best."""
        if not performance_by_hour:
            return []

        # Get hours with performance above threshold
        peak_hours = [
            hour for hour, perf in performance_by_hour.items()
            if perf >= self.PERFORMANCE_THRESHOLD
        ]

        # If no hours above threshold, take top 3
        if not peak_hours:
            sorted_hours = sorted(
                performance_by_hour.items(),
                key=lambda x: x[1],
                reverse=True
            )
            peak_hours = [hour for hour, _ in sorted_hours[:3]]

        return sorted(peak_hours)

    def _determine_optimal_study_time(
        self,
        peak_hours: List[int]
    ) -> Optional[time]:
        """Determine single optimal study start time."""
        if not peak_hours:
            return None

        # Find most common peak hour (or earliest if tie)
        return time(hour=peak_hours[0], minute=0)

    def _analyze_performance_by_day(
        self,
        sessions: List[Dict[str, Any]]
    ) -> Dict[int, float]:
        """Calculate average performance by day of week."""
        performance_by_day = {}

        for day in range(7):  # 0=Monday, 6=Sunday
            day_sessions = [s for s in sessions if s['day_of_week'] == day]
            if day_sessions:
                avg_performance = statistics.mean([s['performance'] for s in day_sessions])
                performance_by_day[day] = float(avg_performance)

        return performance_by_day

    def _identify_best_days(
        self,
        performance_by_day: Dict[int, float]
    ) -> List[str]:
        """Identify best days of week for learning."""
        if not performance_by_day:
            return []

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        # Sort days by performance
        sorted_days = sorted(
            performance_by_day.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Return top 3 days
        return [day_names[day] for day, _ in sorted_days[:3]]

    def _calculate_avg_session_duration(
        self,
        sessions: List[Dict[str, Any]]
    ) -> float:
        """Calculate average session duration in minutes."""
        if not sessions:
            return 30.0  # Default

        return float(statistics.mean([s['duration_minutes'] for s in sessions]))

    def _infer_preferred_session_length(
        self,
        sessions: List[Dict[str, Any]]
    ) -> int:
        """Infer user's preferred session length."""
        if not sessions:
            return 30

        avg_duration = self._calculate_avg_session_duration(sessions)

        # Round to nearest 15 minutes
        return int(round(avg_duration / 15) * 15)

    def _find_most_active_hour(
        self,
        sessions: List[Dict[str, Any]]
    ) -> int:
        """Find hour with most sessions."""
        if not sessions:
            return 19  # Default to 7 PM

        hour_counts = {}
        for session in sessions:
            hour = session['hour']
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        return max(hour_counts, key=hour_counts.get)

    def _find_least_active_hour(
        self,
        sessions: List[Dict[str, Any]]
    ) -> int:
        """Find hour with fewest sessions (during waking hours)."""
        if not sessions:
            return 3  # Default to 3 AM

        # Only consider waking hours (7 AM - 11 PM)
        waking_hours = range(7, 23)
        hour_counts = {h: 0 for h in waking_hours}

        for session in sessions:
            hour = session['hour']
            if hour in waking_hours:
                hour_counts[hour] += 1

        return min(hour_counts, key=hour_counts.get)

    def _identify_typical_study_days(
        self,
        sessions: List[Dict[str, Any]]
    ) -> List[int]:
        """Identify which days user typically studies."""
        if not sessions:
            return [1, 2, 3, 4, 5]  # Default to weekdays

        day_counts = {}
        for session in sessions:
            day = session['day_of_week']
            day_counts[day] = day_counts.get(day, 0) + 1

        # Return days with above-average activity
        avg_count = statistics.mean(list(day_counts.values()))
        return sorted([day for day, count in day_counts.items() if count >= avg_count])

    def _calculate_confidence(self, num_sessions: int) -> float:
        """Calculate confidence in timing profile based on data points."""
        if num_sessions < 10:
            return 0.0
        elif num_sessions < 30:
            return 0.5
        elif num_sessions < 50:
            return 0.7
        else:
            return min(0.9, 0.7 + (num_sessions - 50) / 500)

    def _get_default_profile(self) -> Dict[str, Any]:
        """Return default profile when insufficient data."""
        return {
            'performance_by_hour': {},
            'peak_hours': [],
            'optimal_study_time': None,
            'performance_by_day': {},
            'best_days': [],
            'avg_session_duration': 30.0,
            'preferred_session_length': 30,
            'most_active_hour': None,
            'least_active_hour': None,
            'typical_study_days': [],
            'sessions_analyzed': 0,
            'confidence': 0.0
        }

    async def _store_timing_profile(
        self,
        user_id: int,
        profile: Dict[str, Any],
        db: AsyncSession
    ):
        """Store or update timing profile."""
        stmt = select(UserTimingProfile).where(UserTimingProfile.user_id == user_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.peak_hours = profile['peak_hours']
            existing.optimal_study_time = profile['optimal_study_time']
            existing.best_days = profile['best_days']
            existing.avg_session_duration_minutes = profile['avg_session_duration']
            existing.preferred_session_length = profile['preferred_session_length']
            existing.performance_by_hour = profile['performance_by_hour']
            existing.most_active_hour = profile['most_active_hour']
            existing.least_active_hour = profile['least_active_hour']
            existing.typical_study_days = profile['typical_study_days']
            existing.sessions_analyzed = profile['sessions_analyzed']
            existing.confidence = profile['confidence']
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            timing_profile = UserTimingProfile(
                user_id=user_id,
                peak_hours=profile['peak_hours'],
                optimal_study_time=profile['optimal_study_time'],
                best_days=profile['best_days'],
                avg_session_duration_minutes=profile['avg_session_duration'],
                preferred_session_length=profile['preferred_session_length'],
                performance_by_hour=profile['performance_by_hour'],
                most_active_hour=profile['most_active_hour'],
                least_active_hour=profile['least_active_hour'],
                typical_study_days=profile['typical_study_days'],
                sessions_analyzed=profile['sessions_analyzed'],
                confidence=profile['confidence']
            )
            db.add(timing_profile)

        await db.commit()

    async def should_send_intervention_now(
        self,
        user_id: int,
        current_time: datetime,
        db: AsyncSession
    ) -> bool:
        """
        Determine if now is a good time to send intervention based on user's patterns.
        """
        stmt = select(UserTimingProfile).where(UserTimingProfile.user_id == user_id)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()

        if not profile or profile.confidence < 0.5:
            # Not enough data, use general heuristics
            return self._use_general_timing_heuristics(current_time)

        current_hour = current_time.hour
        current_day = current_time.weekday()

        # Check if current hour is a peak hour
        if profile.peak_hours and current_hour in profile.peak_hours:
            return True

        # Check if current day is a typical study day
        if profile.typical_study_days and current_day in profile.typical_study_days:
            # If it's a study day, check if close to active hour
            if profile.most_active_hour:
                time_diff = abs(current_hour - profile.most_active_hour)
                if time_diff <= 1:  # Within 1 hour of typical time
                    return True

        return False

    def _use_general_timing_heuristics(self, current_time: datetime) -> bool:
        """Use general good practice timing when no user-specific data."""
        hour = current_time.hour

        # Good times: morning (7-9), lunch (12-13), evening (18-21)
        good_hours = list(range(7, 10)) + list(range(12, 14)) + list(range(18, 22))

        return hour in good_hours

    async def get_recommended_intervention_time(
        self,
        user_id: int,
        db: AsyncSession
    ) -> Optional[time]:
        """Get recommended time to send intervention for maximum engagement."""
        stmt = select(UserTimingProfile).where(UserTimingProfile.user_id == user_id)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile and profile.optimal_study_time:
            return profile.optimal_study_time

        # Default to 7 PM if no profile
        return time(hour=19, minute=0)


# Global singleton
timing_optimizer = TimingOptimizer()
