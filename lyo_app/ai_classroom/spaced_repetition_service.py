"""
Spaced Repetition Service - Unified SM-2 Algorithm Implementation

This service consolidates spaced repetition across the app:
- AI Classroom review scheduling (ReviewSchedule model)
- Personalization retention tracking
- SM-2 algorithm with extensions

The SM-2 Algorithm:
1. Calculate new easiness factor (EF)
2. Determine new interval based on quality and repetition number
3. Schedule next review date
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_

from lyo_app.ai_classroom.models import ReviewSchedule, MasteryState, LearningNode

logger = logging.getLogger(__name__)


class ReviewQuality(IntEnum):
    """
    SM-2 Quality ratings:
    0 - Complete blackout, no memory
    1 - Incorrect response, but upon seeing correct answer, remembered
    2 - Incorrect response, but correct answer seemed easy to recall
    3 - Correct response with serious difficulty
    4 - Correct response after hesitation
    5 - Perfect response with no hesitation
    """
    BLACKOUT = 0
    INCORRECT_BUT_REMEMBERED = 1
    INCORRECT_EASY_RECALL = 2
    CORRECT_DIFFICULT = 3
    CORRECT_HESITATION = 4
    PERFECT = 5


@dataclass
class ReviewResult:
    """Result after processing a review."""
    next_review_date: datetime
    new_interval_days: int
    new_easiness_factor: float
    repetition_number: int
    streak: int
    is_graduated: bool  # Interval > 30 days = mastered


@dataclass
class ReviewStats:
    """User's review statistics."""
    total_items: int
    due_today: int
    overdue: int
    upcoming_week: int
    average_retention: float
    current_streak: int
    longest_streak: int


class SM2Algorithm:
    """
    Implementation of the SuperMemo SM-2 algorithm.
    
    Formula:
    EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    
    Where:
    - EF = easiness factor (minimum 1.3)
    - q = quality of response (0-5)
    
    Interval calculation:
    - rep 1: 1 day
    - rep 2: 6 days
    - rep n: I(n-1) * EF
    """
    
    MIN_EASINESS_FACTOR = 1.3
    GRADUATED_INTERVAL = 30  # Days to be considered "mastered"
    
    @classmethod
    def calculate_new_ef(cls, current_ef: float, quality: int) -> float:
        """Calculate new easiness factor based on response quality."""
        q = max(0, min(5, quality))
        new_ef = current_ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        return max(cls.MIN_EASINESS_FACTOR, new_ef)
    
    @classmethod
    def calculate_interval(
        cls,
        repetition: int,
        easiness_factor: float,
        previous_interval: int,
        quality: int
    ) -> int:
        """Calculate the next review interval in days."""
        # If quality < 3, reset to beginning
        if quality < 3:
            return 1
        
        if repetition == 0:
            return 1
        elif repetition == 1:
            return 6
        else:
            # I(n) = I(n-1) * EF
            return max(1, round(previous_interval * easiness_factor))
    
    @classmethod
    def process_review(
        cls,
        current_ef: float,
        current_interval: int,
        current_repetition: int,
        quality: int,
        current_streak: int
    ) -> Tuple[float, int, int, int]:
        """
        Process a review and return updated values.
        
        Returns:
            (new_ef, new_interval, new_repetition, new_streak)
        """
        new_ef = cls.calculate_new_ef(current_ef, quality)
        
        if quality < 3:
            # Failed - reset
            new_interval = 1
            new_repetition = 0
            new_streak = 0
        else:
            # Success
            new_repetition = current_repetition + 1
            new_interval = cls.calculate_interval(
                new_repetition, new_ef, current_interval, quality
            )
            new_streak = current_streak + 1
        
        return new_ef, new_interval, new_repetition, new_streak


class SpacedRepetitionService:
    """
    Service for managing spaced repetition reviews.
    
    Provides:
    - Scheduling items for review
    - Processing review responses
    - Getting due items
    - Statistics and analytics
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.algorithm = SM2Algorithm()
    
    # =========================================================================
    # SCHEDULING
    # =========================================================================
    
    async def schedule_item(
        self,
        user_id: str,
        node_id: Optional[str] = None,
        concept_id: Optional[str] = None,
        initial_quality: int = 3
    ) -> ReviewSchedule:
        """
        Add an item to the review schedule.
        
        At least one of node_id or concept_id must be provided.
        """
        if not node_id and not concept_id:
            raise ValueError("Must provide node_id or concept_id")
        
        # Check if already scheduled
        conditions = [ReviewSchedule.user_id == user_id]
        if node_id:
            conditions.append(ReviewSchedule.node_id == node_id)
        if concept_id:
            conditions.append(ReviewSchedule.concept_id == concept_id)
        
        result = await self.db.execute(
            select(ReviewSchedule).where(and_(*conditions))
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Reactivate if inactive
            if not existing.is_active:
                existing.is_active = True
                existing.next_review_at = datetime.utcnow() + timedelta(days=1)
                await self.db.commit()
            return existing
        
        # Create new schedule
        schedule = ReviewSchedule(
            user_id=user_id,
            node_id=node_id,
            concept_id=concept_id,
            easiness_factor=2.5,
            interval_days=1,
            repetition_number=0,
            next_review_at=datetime.utcnow() + timedelta(days=1),
            last_quality=initial_quality,
            streak=0,
            is_active=True
        )
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule
    
    async def process_review(
        self,
        user_id: str,
        schedule_id: str,
        quality: int
    ) -> ReviewResult:
        """
        Process a review response using SM-2 algorithm.
        
        Args:
            user_id: User ID
            schedule_id: Review schedule ID
            quality: Response quality (0-5)
        
        Returns:
            ReviewResult with updated scheduling info
        """
        result = await self.db.execute(
            select(ReviewSchedule)
            .where(
                and_(
                    ReviewSchedule.id == schedule_id,
                    ReviewSchedule.user_id == user_id
                )
            )
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise ValueError("Schedule not found")
        
        # Apply SM-2 algorithm
        new_ef, new_interval, new_rep, new_streak = self.algorithm.process_review(
            schedule.easiness_factor,
            schedule.interval_days,
            schedule.repetition_number,
            quality,
            schedule.streak
        )
        
        # Update schedule
        schedule.easiness_factor = new_ef
        schedule.interval_days = new_interval
        schedule.repetition_number = new_rep
        schedule.streak = new_streak
        schedule.last_quality = quality
        schedule.last_reviewed_at = datetime.utcnow()
        schedule.next_review_at = datetime.utcnow() + timedelta(days=new_interval)
        
        await self.db.commit()
        
        return ReviewResult(
            next_review_date=schedule.next_review_at,
            new_interval_days=new_interval,
            new_easiness_factor=new_ef,
            repetition_number=new_rep,
            streak=new_streak,
            is_graduated=new_interval >= self.algorithm.GRADUATED_INTERVAL
        )
    
    # =========================================================================
    # RETRIEVAL
    # =========================================================================
    
    async def get_due_items(
        self,
        user_id: str,
        limit: int = 20,
        include_overdue: bool = True
    ) -> List[ReviewSchedule]:
        """Get items due for review today."""
        now = datetime.utcnow()
        
        query = (
            select(ReviewSchedule)
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True,
                    ReviewSchedule.next_review_at <= now
                )
            )
            .order_by(ReviewSchedule.next_review_at)
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_upcoming_items(
        self,
        user_id: str,
        days_ahead: int = 7
    ) -> List[ReviewSchedule]:
        """Get items scheduled for review in the next N days."""
        now = datetime.utcnow()
        future = now + timedelta(days=days_ahead)
        
        result = await self.db.execute(
            select(ReviewSchedule)
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True,
                    ReviewSchedule.next_review_at > now,
                    ReviewSchedule.next_review_at <= future
                )
            )
            .order_by(ReviewSchedule.next_review_at)
        )
        return list(result.scalars().all())
    
    async def get_item_with_node(
        self,
        schedule_id: str
    ) -> Tuple[ReviewSchedule, Optional[LearningNode]]:
        """Get a review schedule with its associated node."""
        result = await self.db.execute(
            select(ReviewSchedule)
            .where(ReviewSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        
        if not schedule:
            raise ValueError("Schedule not found")
        
        node = None
        if schedule.node_id:
            node_result = await self.db.execute(
                select(LearningNode)
                .where(LearningNode.id == schedule.node_id)
            )
            node = node_result.scalar_one_or_none()
        
        return schedule, node
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    async def get_stats(self, user_id: str) -> ReviewStats:
        """Get user's review statistics."""
        now = datetime.utcnow()
        week_later = now + timedelta(days=7)
        
        # Total items
        total_result = await self.db.execute(
            select(func.count(ReviewSchedule.id))
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True
                )
            )
        )
        total = total_result.scalar() or 0
        
        # Due today
        due_result = await self.db.execute(
            select(func.count(ReviewSchedule.id))
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True,
                    ReviewSchedule.next_review_at <= now
                )
            )
        )
        due_today = due_result.scalar() or 0
        
        # Overdue (more than 1 day past due)
        yesterday = now - timedelta(days=1)
        overdue_result = await self.db.execute(
            select(func.count(ReviewSchedule.id))
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True,
                    ReviewSchedule.next_review_at < yesterday
                )
            )
        )
        overdue = overdue_result.scalar() or 0
        
        # Upcoming week
        upcoming_result = await self.db.execute(
            select(func.count(ReviewSchedule.id))
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.is_active == True,
                    ReviewSchedule.next_review_at > now,
                    ReviewSchedule.next_review_at <= week_later
                )
            )
        )
        upcoming = upcoming_result.scalar() or 0
        
        # Average retention (based on last quality scores)
        avg_result = await self.db.execute(
            select(func.avg(ReviewSchedule.last_quality))
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.last_reviewed_at.isnot(None)
                )
            )
        )
        avg_quality = avg_result.scalar() or 3.0
        # Convert 0-5 scale to 0-100% retention
        avg_retention = (avg_quality / 5.0) * 100
        
        # Current streak (max consecutive streak)
        streak_result = await self.db.execute(
            select(func.max(ReviewSchedule.streak))
            .where(ReviewSchedule.user_id == user_id)
        )
        current_streak = streak_result.scalar() or 0
        
        return ReviewStats(
            total_items=total,
            due_today=due_today,
            overdue=overdue,
            upcoming_week=upcoming,
            average_retention=avg_retention,
            current_streak=current_streak,
            longest_streak=current_streak  # Would need separate tracking
        )
    
    # =========================================================================
    # INTERLEAVING
    # =========================================================================
    
    async def get_interleaved_queue(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[ReviewSchedule]:
        """
        Get a queue of items interleaved by concept.
        
        Interleaving improves retention by mixing different concepts
        rather than reviewing the same concept repeatedly.
        """
        due_items = await self.get_due_items(user_id, limit=limit * 2)
        
        if len(due_items) <= 1:
            return due_items[:limit]
        
        # Group by concept
        by_concept: Dict[str, List[ReviewSchedule]] = {}
        no_concept: List[ReviewSchedule] = []
        
        for item in due_items:
            if item.concept_id:
                if item.concept_id not in by_concept:
                    by_concept[item.concept_id] = []
                by_concept[item.concept_id].append(item)
            else:
                no_concept.append(item)
        
        # Interleave: take one from each concept in round-robin
        result = []
        concept_lists = list(by_concept.values()) + ([no_concept] if no_concept else [])
        indices = [0] * len(concept_lists)
        
        while len(result) < limit and any(
            i < len(lst) for i, lst in zip(indices, concept_lists)
        ):
            for i, lst in enumerate(concept_lists):
                if indices[i] < len(lst) and len(result) < limit:
                    result.append(lst[indices[i]])
                    indices[i] += 1
        
        return result
    
    # =========================================================================
    # SYNCHRONIZATION
    # =========================================================================
    
    async def sync_with_mastery(
        self,
        user_id: str,
        concept_id: str
    ) -> None:
        """
        Sync review schedule with mastery state.
        
        If mastery is high (>0.8), increase interval.
        If mastery is low (<0.3), reset schedule.
        """
        # Get mastery state
        mastery_result = await self.db.execute(
            select(MasteryState)
            .where(
                and_(
                    MasteryState.user_id == user_id,
                    MasteryState.concept_id == concept_id
                )
            )
        )
        mastery = mastery_result.scalar_one_or_none()
        
        if not mastery:
            return
        
        # Get review schedule
        schedule_result = await self.db.execute(
            select(ReviewSchedule)
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.concept_id == concept_id
                )
            )
        )
        schedule = schedule_result.scalar_one_or_none()
        
        if not schedule:
            return
        
        # Adjust based on mastery
        if mastery.mastery_score >= 0.8 and schedule.interval_days < 14:
            # High mastery - boost interval
            schedule.interval_days = max(schedule.interval_days, 14)
            schedule.next_review_at = datetime.utcnow() + timedelta(days=schedule.interval_days)
        
        elif mastery.mastery_score < 0.3:
            # Low mastery - reset
            schedule.interval_days = 1
            schedule.repetition_number = 0
            schedule.next_review_at = datetime.utcnow() + timedelta(days=1)
        
        await self.db.commit()


def get_spaced_repetition_service(db: AsyncSession) -> SpacedRepetitionService:
    """Factory function for dependency injection."""
    return SpacedRepetitionService(db)
