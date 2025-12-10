"""
Interaction Service - Handles user responses to knowledge checks

This service:
1. Evaluates user answers using various interaction types
2. Updates mastery scores using Bayesian updates
3. Detects misconceptions from error patterns
4. Schedules items for spaced repetition review
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from lyo_app.ai_classroom.models import (
    LearningNode, InteractionAttempt, MasteryState, Misconception,
    ReviewSchedule, NodeType, InteractionType
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of evaluating a user's answer."""
    is_correct: bool
    score: float  # 0.0 to 1.0 for partial credit
    feedback: str
    correct_answer: Optional[str]
    detected_misconception_id: Optional[str]
    explanation: Optional[str]


@dataclass
class MasteryUpdate:
    """Result of updating mastery."""
    old_score: float
    new_score: float
    delta: float
    confidence: float
    trend: str


class InteractionEvaluator:
    """Evaluates different types of interactions."""
    
    @staticmethod
    def evaluate_multiple_choice(
        content: Dict[str, Any],
        answer_id: str
    ) -> EvaluationResult:
        """Evaluate a multiple choice answer."""
        options = content.get("options", [])
        selected = None
        correct = None
        
        for opt in options:
            if opt.get("id") == answer_id:
                selected = opt
            if opt.get("is_correct", False):
                correct = opt
        
        if not selected:
            return EvaluationResult(
                is_correct=False,
                score=0.0,
                feedback="Invalid answer selection",
                correct_answer=correct.get("label") if correct else None,
                detected_misconception_id=None,
                explanation=content.get("explanation")
            )
        
        is_correct = selected.get("is_correct", False)
        return EvaluationResult(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback=selected.get("feedback", ""),
            correct_answer=correct.get("label") if correct else None,
            detected_misconception_id=selected.get("misconception_tag"),
            explanation=content.get("explanation")
        )
    
    @staticmethod
    def evaluate_true_false(
        content: Dict[str, Any],
        answer: str
    ) -> EvaluationResult:
        """Evaluate a true/false answer."""
        correct_answer = content.get("correct_answer", "true")
        is_correct = answer.lower() == correct_answer.lower()
        
        return EvaluationResult(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback=content.get("correct_feedback" if is_correct else "wrong_feedback", ""),
            correct_answer=correct_answer,
            detected_misconception_id=None if is_correct else content.get("misconception_tag"),
            explanation=content.get("explanation")
        )
    
    @staticmethod
    def evaluate_slider(
        content: Dict[str, Any],
        answer: float
    ) -> EvaluationResult:
        """Evaluate a slider/numeric answer with tolerance."""
        correct_value = content.get("correct_value", 0)
        tolerance = content.get("tolerance", 0.1)
        
        diff = abs(answer - correct_value)
        is_exact = diff <= tolerance
        
        # Partial credit based on proximity
        max_diff = content.get("max_value", 100) - content.get("min_value", 0)
        score = max(0, 1 - (diff / max_diff)) if not is_exact else 1.0
        
        return EvaluationResult(
            is_correct=is_exact,
            score=score,
            feedback=f"Correct: {correct_value}" if not is_exact else "Exactly right!",
            correct_answer=str(correct_value),
            detected_misconception_id=None,
            explanation=content.get("explanation")
        )
    
    @staticmethod
    def evaluate_drag_match(
        content: Dict[str, Any],
        answer: Dict[str, str]  # {item_id: target_id}
    ) -> EvaluationResult:
        """Evaluate a drag-and-match answer."""
        correct_mapping = content.get("correct_mapping", {})
        
        correct_count = 0
        total = len(correct_mapping)
        
        for item_id, target_id in answer.items():
            if correct_mapping.get(item_id) == target_id:
                correct_count += 1
        
        score = correct_count / total if total > 0 else 0
        is_correct = score >= 1.0
        
        return EvaluationResult(
            is_correct=is_correct,
            score=score,
            feedback=f"{correct_count}/{total} correct" if not is_correct else "All matched correctly!",
            correct_answer=str(correct_mapping),
            detected_misconception_id=None,
            explanation=content.get("explanation")
        )
    
    @staticmethod
    def evaluate_short_answer(
        content: Dict[str, Any],
        answer: str
    ) -> EvaluationResult:
        """Evaluate a short answer against acceptable answers."""
        acceptable = content.get("acceptable_answers", [])
        answer_normalized = answer.lower().strip()
        
        for acc in acceptable:
            if answer_normalized == acc.lower().strip():
                return EvaluationResult(
                    is_correct=True,
                    score=1.0,
                    feedback="Correct!",
                    correct_answer=acc,
                    detected_misconception_id=None,
                    explanation=content.get("explanation")
                )
        
        # Check for partial matches
        for acc in acceptable:
            if answer_normalized in acc.lower() or acc.lower() in answer_normalized:
                return EvaluationResult(
                    is_correct=False,
                    score=0.5,
                    feedback="Close, but not quite right.",
                    correct_answer=acceptable[0] if acceptable else None,
                    detected_misconception_id=None,
                    explanation=content.get("explanation")
                )
        
        return EvaluationResult(
            is_correct=False,
            score=0.0,
            feedback=content.get("wrong_feedback", "Incorrect."),
            correct_answer=acceptable[0] if acceptable else None,
            detected_misconception_id=content.get("misconception_tag"),
            explanation=content.get("explanation")
        )


class InteractionService:
    """Service for handling user interactions with knowledge checks."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.evaluator = InteractionEvaluator()
    
    async def evaluate_answer(
        self,
        node: LearningNode,
        answer: Any
    ) -> EvaluationResult:
        """
        Evaluate a user's answer to an interaction.
        
        Args:
            node: The interaction node
            answer: User's answer (type varies by interaction type)
        
        Returns:
            EvaluationResult with correctness, score, and feedback
        """
        if node.node_type != NodeType.INTERACTION.value:
            raise ValueError("Node is not an interaction")
        
        content = node.content or {}
        interaction_type = node.interaction_type
        
        if interaction_type == InteractionType.MULTIPLE_CHOICE.value:
            return self.evaluator.evaluate_multiple_choice(content, str(answer))
        
        elif interaction_type == InteractionType.TRUE_FALSE.value:
            return self.evaluator.evaluate_true_false(content, str(answer))
        
        elif interaction_type == InteractionType.SLIDER.value:
            return self.evaluator.evaluate_slider(content, float(answer))
        
        elif interaction_type == InteractionType.DRAG_MATCH.value:
            return self.evaluator.evaluate_drag_match(content, answer)
        
        elif interaction_type == InteractionType.SHORT_ANSWER.value:
            return self.evaluator.evaluate_short_answer(content, str(answer))
        
        else:
            # Default to multiple choice logic
            return self.evaluator.evaluate_multiple_choice(content, str(answer))
    
    async def record_attempt(
        self,
        user_id: str,
        node: LearningNode,
        answer: Any,
        result: EvaluationResult,
        time_taken_seconds: float
    ) -> InteractionAttempt:
        """Record an interaction attempt in the database."""
        # Count previous attempts
        count_result = await self.db.execute(
            select(func.count(InteractionAttempt.id))
            .where(
                and_(
                    InteractionAttempt.user_id == user_id,
                    InteractionAttempt.node_id == node.id
                )
            )
        )
        previous_attempts = count_result.scalar() or 0
        
        attempt = InteractionAttempt(
            user_id=user_id,
            node_id=node.id,
            user_answer=str(answer),
            is_correct=result.is_correct,
            time_taken_seconds=time_taken_seconds,
            attempt_number=previous_attempts + 1,
            detected_misconception_id=result.detected_misconception_id
        )
        self.db.add(attempt)
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt
    
    async def update_mastery_bayesian(
        self,
        user_id: str,
        concept_id: str,
        is_correct: bool,
        score: float = None,
        time_taken: float = None
    ) -> MasteryUpdate:
        """
        Update mastery using a Bayesian-inspired approach.
        
        Factors:
        - Previous mastery score (prior)
        - Current performance (likelihood)
        - Confidence based on number of attempts
        - Time taken (faster correct = higher confidence)
        """
        # Get or create mastery state
        result = await self.db.execute(
            select(MasteryState)
            .where(
                and_(
                    MasteryState.user_id == user_id,
                    MasteryState.concept_id == concept_id
                )
            )
        )
        mastery = result.scalar_one_or_none()
        
        old_score = 0.0
        if not mastery:
            mastery = MasteryState(
                user_id=user_id,
                concept_id=concept_id,
                mastery_score=0.5,  # Start with uncertainty
                confidence=0.3
            )
            self.db.add(mastery)
        else:
            old_score = mastery.mastery_score
        
        # Update counts
        mastery.attempts += 1
        if is_correct:
            mastery.correct_count += 1
            mastery.last_correct = datetime.utcnow()
        else:
            mastery.incorrect_count += 1
        
        # Calculate new mastery (Bayesian-ish update)
        score_to_use = score if score is not None else (1.0 if is_correct else 0.0)
        
        # Learning rate decreases with confidence
        alpha = max(0.1, 0.5 * (1 - mastery.confidence))
        
        # Update mastery score
        new_score = mastery.mastery_score * (1 - alpha) + score_to_use * alpha
        
        # Update confidence (increases with more attempts)
        mastery.confidence = min(0.95, mastery.confidence + 0.05)
        
        # Adjust for time taken (faster correct = boost)
        if time_taken and is_correct:
            expected_time = 30  # seconds
            if time_taken < expected_time:
                speed_bonus = 0.02 * (1 - time_taken / expected_time)
                new_score = min(1.0, new_score + speed_bonus)
        
        # Clamp score
        mastery.mastery_score = max(0.0, min(1.0, new_score))
        
        # Update trend
        mastery.trend = self._calculate_trend(
            mastery.correct_count, 
            mastery.attempts,
            old_score,
            mastery.mastery_score
        )
        mastery.last_seen = datetime.utcnow()
        
        await self.db.commit()
        
        return MasteryUpdate(
            old_score=old_score,
            new_score=mastery.mastery_score,
            delta=mastery.mastery_score - old_score,
            confidence=mastery.confidence,
            trend=mastery.trend
        )
    
    def _calculate_trend(
        self,
        correct: int,
        total: int,
        old_score: float,
        new_score: float
    ) -> str:
        """Calculate mastery trend."""
        if total < 3:
            return "stable"
        
        delta = new_score - old_score
        if delta > 0.05:
            return "improving"
        elif delta < -0.05:
            return "declining"
        return "stable"
    
    async def schedule_for_review(
        self,
        user_id: str,
        node_id: str,
        concept_id: str,
        initial_quality: int = 3
    ) -> ReviewSchedule:
        """
        Add an item to the spaced repetition schedule.
        
        Uses SM-2 algorithm defaults.
        """
        # Check if already scheduled
        result = await self.db.execute(
            select(ReviewSchedule)
            .where(
                and_(
                    ReviewSchedule.user_id == user_id,
                    ReviewSchedule.node_id == node_id
                )
            )
        )
        schedule = result.scalar_one_or_none()
        
        if schedule:
            return schedule  # Already scheduled
        
        schedule = ReviewSchedule(
            user_id=user_id,
            node_id=node_id,
            concept_id=concept_id,
            easiness_factor=2.5,
            interval_days=1,
            repetition_number=0,
            next_review_at=datetime.utcnow() + timedelta(days=1),
            last_quality=initial_quality,
            is_active=True
        )
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule
    
    async def detect_misconception(
        self,
        node: LearningNode,
        answer: Any
    ) -> Optional[Misconception]:
        """
        Detect if the user's answer reveals a known misconception.
        
        Checks the misconception database and updates occurrence counts.
        """
        content = node.content or {}
        options = content.get("options", [])
        
        # Find the selected option's misconception tag
        misconception_tag = None
        for opt in options:
            if opt.get("id") == str(answer):
                misconception_tag = opt.get("misconception_tag")
                break
        
        if not misconception_tag or not node.concept_id:
            return None
        
        # Look up the misconception
        result = await self.db.execute(
            select(Misconception)
            .where(
                and_(
                    Misconception.concept_id == node.concept_id,
                    Misconception.label == misconception_tag
                )
            )
        )
        misconception = result.scalar_one_or_none()
        
        if misconception:
            # Update occurrence count
            misconception.occurrence_count += 1
            await self.db.commit()
        
        return misconception


def get_interaction_service(db: AsyncSession) -> InteractionService:
    """Factory function for dependency injection."""
    return InteractionService(db)
