"""
Graph Service - Learning Path Navigation Engine

This service handles:
1. Graph traversal (finding next nodes based on conditions)
2. Adaptive routing (choosing paths based on mastery)
3. Progress tracking
4. Prerequisite validation
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from lyo_app.ai_classroom.models import (
    GraphCourse, LearningNode, LearningEdge, MasteryState, CourseProgress,
    InteractionAttempt, NodeType, EdgeCondition
)

logger = logging.getLogger(__name__)


class GraphService:
    """
    Service for navigating the learning graph.
    
    The graph is a directed graph where:
    - Nodes are learning content (narrative, interaction, remediation)
    - Edges define possible transitions with conditions
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # COURSE LOADING
    # =========================================================================
    
    async def get_course_with_graph(self, course_id: str) -> Optional[GraphCourse]:
        """Load a course with all its nodes and edges."""
        result = await self.db.execute(
            select(GraphCourse)
            .options(
                selectinload(GraphCourse.nodes),
                selectinload(GraphCourse.edges)
            )
            .where(GraphCourse.id == course_id)
        )
        return result.scalar_one_or_none()
    
    async def get_node(self, node_id: str) -> Optional[LearningNode]:
        """Get a single node by ID."""
        result = await self.db.execute(
            select(LearningNode).where(LearningNode.id == node_id)
        )
        return result.scalar_one_or_none()
    
    async def get_nodes_by_course(self, course_id: str) -> List[LearningNode]:
        """Get all nodes for a course, ordered by sequence."""
        result = await self.db.execute(
            select(LearningNode)
            .where(LearningNode.course_id == course_id)
            .order_by(LearningNode.sequence_order)
        )
        return result.scalars().all()
    
    # =========================================================================
    # GRAPH NAVIGATION
    # =========================================================================
    
    async def get_next_nodes(
        self,
        current_node_id: str,
        user_id: str,
        interaction_result: Optional[bool] = None
    ) -> List[Tuple[LearningNode, float]]:
        """
        Get possible next nodes with their weights.
        
        Args:
            current_node_id: The node the user just completed
            user_id: For mastery-based routing
            interaction_result: True if passed, False if failed, None if not an interaction
        
        Returns:
            List of (node, weight) tuples, sorted by weight descending
        """
        # Get all outgoing edges
        edges_result = await self.db.execute(
            select(LearningEdge)
            .options(selectinload(LearningEdge.to_node))
            .where(LearningEdge.from_node_id == current_node_id)
        )
        edges = edges_result.scalars().all()
        
        if not edges:
            return []
        
        # Filter edges based on conditions
        valid_edges = []
        for edge in edges:
            is_valid, weight = await self._evaluate_edge_condition(
                edge, user_id, interaction_result
            )
            if is_valid:
                valid_edges.append((edge.to_node, edge.weight * weight))
        
        # Sort by weight (highest first)
        valid_edges.sort(key=lambda x: x[1], reverse=True)
        return valid_edges
    
    async def get_best_next_node(
        self,
        current_node_id: str,
        user_id: str,
        interaction_result: Optional[bool] = None
    ) -> Optional[LearningNode]:
        """Get the single best next node."""
        next_nodes = await self.get_next_nodes(
            current_node_id, user_id, interaction_result
        )
        return next_nodes[0][0] if next_nodes else None
    
    async def _evaluate_edge_condition(
        self,
        edge: LearningEdge,
        user_id: str,
        interaction_result: Optional[bool]
    ) -> Tuple[bool, float]:
        """
        Evaluate if an edge condition is met.
        
        Returns:
            (is_valid, weight_multiplier)
        """
        condition = edge.condition
        
        if condition == EdgeCondition.ALWAYS.value:
            return True, 1.0
        
        if condition == EdgeCondition.PASS.value:
            if interaction_result is True:
                return True, 1.0
            return False, 0.0
        
        if condition == EdgeCondition.FAIL.value:
            if interaction_result is False:
                return True, 1.0
            return False, 0.0
        
        if condition == EdgeCondition.OPTIONAL.value:
            return True, 0.5  # Lower weight for optional paths
        
        if condition in [EdgeCondition.MASTERY_LOW.value, EdgeCondition.MASTERY_HIGH.value]:
            # Get user's mastery for the relevant concept
            to_node = edge.to_node
            if to_node.concept_id:
                mastery = await self._get_user_mastery(user_id, to_node.concept_id)
                threshold = edge.mastery_threshold or 0.7
                
                if condition == EdgeCondition.MASTERY_LOW.value:
                    return mastery < threshold, 1.0
                else:
                    return mastery >= threshold, 1.0
        
        return True, 1.0
    
    async def _get_user_mastery(self, user_id: str, concept_id: str) -> float:
        """Get user's mastery score for a concept."""
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
        return mastery.mastery_score if mastery else 0.0
    
    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================
    
    async def get_or_create_progress(
        self,
        user_id: str,
        course_id: str
    ) -> CourseProgress:
        """Get or create progress tracking for a user in a course."""
        result = await self.db.execute(
            select(CourseProgress)
            .where(
                and_(
                    CourseProgress.user_id == user_id,
                    CourseProgress.course_id == course_id
                )
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            # Get the course to find entry node
            course = await self.get_course_with_graph(course_id)
            if not course:
                raise ValueError(f"Course {course_id} not found")
            
            progress = CourseProgress(
                user_id=user_id,
                course_id=course_id,
                current_node_id=course.entry_node_id,
                completed_node_ids=[],
                status="in_progress"
            )
            self.db.add(progress)
            await self.db.commit()
            await self.db.refresh(progress)
        
        return progress
    
    async def advance_progress(
        self,
        user_id: str,
        course_id: str,
        completed_node_id: str,
        next_node_id: Optional[str],
        time_spent_seconds: int = 0
    ) -> CourseProgress:
        """Advance the user's progress in the course."""
        progress = await self.get_or_create_progress(user_id, course_id)
        
        # Add to completed if not already there
        if completed_node_id not in progress.completed_node_ids:
            progress.completed_node_ids = progress.completed_node_ids + [completed_node_id]
        
        # Update current position
        progress.current_node_id = next_node_id
        progress.total_time_seconds += time_spent_seconds
        progress.last_active_at = datetime.utcnow()
        
        # Calculate completion percentage
        total_nodes = await self._count_course_nodes(course_id)
        progress.completion_percentage = len(progress.completed_node_ids) / total_nodes * 100 if total_nodes > 0 else 0
        
        # Check if complete
        if next_node_id is None:
            progress.status = "completed"
            progress.completed_at = datetime.utcnow()
        
        await self.db.commit()
        return progress
    
    async def _count_course_nodes(self, course_id: str) -> int:
        """Count total nodes in a course (excluding remediation)."""
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(LearningNode.id))
            .where(
                and_(
                    LearningNode.course_id == course_id,
                    LearningNode.node_type != NodeType.REMEDIATION.value
                )
            )
        )
        return result.scalar() or 0
    
    # =========================================================================
    # INTERACTION HANDLING
    # =========================================================================
    
    async def record_interaction_attempt(
        self,
        user_id: str,
        node_id: str,
        user_answer: str,
        is_correct: bool,
        time_taken_seconds: float,
        detected_misconception_id: Optional[str] = None
    ) -> InteractionAttempt:
        """Record an interaction attempt."""
        # Count previous attempts
        count_result = await self.db.execute(
            select(InteractionAttempt)
            .where(
                and_(
                    InteractionAttempt.user_id == user_id,
                    InteractionAttempt.node_id == node_id
                )
            )
        )
        previous_attempts = len(count_result.scalars().all())
        
        attempt = InteractionAttempt(
            user_id=user_id,
            node_id=node_id,
            user_answer=user_answer,
            is_correct=is_correct,
            time_taken_seconds=time_taken_seconds,
            attempt_number=previous_attempts + 1,
            detected_misconception_id=detected_misconception_id
        )
        self.db.add(attempt)
        await self.db.commit()
        return attempt
    
    async def update_mastery(
        self,
        user_id: str,
        concept_id: str,
        is_correct: bool
    ) -> MasteryState:
        """Update user's mastery based on interaction result."""
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
        
        if not mastery:
            mastery = MasteryState(
                user_id=user_id,
                concept_id=concept_id,
                mastery_score=0.0,
                confidence=0.5
            )
            self.db.add(mastery)
        
        # Update counts
        mastery.attempts += 1
        if is_correct:
            mastery.correct_count += 1
            mastery.last_correct = datetime.utcnow()
        else:
            mastery.incorrect_count += 1
        
        # Calculate new mastery score (simple Bayesian-ish update)
        # More sophisticated: use IRT or BKT
        mastery.mastery_score = self._calculate_mastery(
            mastery.correct_count,
            mastery.attempts,
            mastery.mastery_score
        )
        
        # Update trend
        mastery.trend = self._calculate_trend(mastery)
        mastery.last_seen = datetime.utcnow()
        
        await self.db.commit()
        return mastery
    
    def _calculate_mastery(
        self,
        correct: int,
        total: int,
        previous_score: float
    ) -> float:
        """
        Calculate mastery score using a weighted approach.
        
        Combines:
        - Raw accuracy
        - Previous score (for smoothing)
        - Recency bias
        """
        if total == 0:
            return 0.0
        
        raw_accuracy = correct / total
        
        # Weighted average with previous score (more weight on recent)
        alpha = 0.7  # Weight for new evidence
        new_score = alpha * raw_accuracy + (1 - alpha) * previous_score
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, new_score))
    
    def _calculate_trend(self, mastery: MasteryState) -> str:
        """Determine if user is improving, declining, or stable."""
        if mastery.attempts < 3:
            return "stable"
        
        # Look at recent accuracy vs overall
        # In production, you'd track a rolling window
        recent_accuracy = mastery.correct_count / mastery.attempts if mastery.attempts > 0 else 0
        
        if recent_accuracy > mastery.mastery_score + 0.1:
            return "improving"
        elif recent_accuracy < mastery.mastery_score - 0.1:
            return "declining"
        return "stable"
    
    # =========================================================================
    # REMEDIATION LOGIC
    # =========================================================================
    
    async def should_trigger_remediation(
        self,
        user_id: str,
        node_id: str
    ) -> Tuple[bool, int]:
        """
        Check if remediation should be triggered and how many attempts remain.
        
        Returns:
            (should_remediate, remaining_budget)
        """
        node = await self.get_node(node_id)
        if not node:
            return False, 0
        
        # Count remediation attempts for this node
        result = await self.db.execute(
            select(InteractionAttempt)
            .where(
                and_(
                    InteractionAttempt.user_id == user_id,
                    InteractionAttempt.node_id == node_id,
                    InteractionAttempt.remediation_shown == True
                )
            )
        )
        remediation_count = len(result.scalars().all())
        
        remaining = node.remediation_budget - remediation_count
        should_remediate = remaining > 0
        
        return should_remediate, remaining
    
    async def get_fallback_node(self, node_id: str) -> Optional[LearningNode]:
        """Get the gold-standard fallback node for remediation."""
        node = await self.get_node(node_id)
        if node and node.fallback_node_id:
            return await self.get_node(node.fallback_node_id)
        return None
    
    # =========================================================================
    # LOOKAHEAD (for pre-loading assets)
    # =========================================================================
    
    async def get_lookahead_nodes(
        self,
        current_node_id: str,
        user_id: str,
        count: int = 3
    ) -> List[LearningNode]:
        """
        Get the next N likely nodes for pre-loading assets.
        
        This is crucial for the "Netflix" experience - we pre-load
        upcoming scenes while the user watches the current one.
        """
        lookahead = []
        visited = {current_node_id}
        queue = [current_node_id]
        
        while queue and len(lookahead) < count:
            node_id = queue.pop(0)
            next_nodes = await self.get_next_nodes(node_id, user_id)
            
            for node, weight in next_nodes:
                if node.id not in visited:
                    visited.add(node.id)
                    lookahead.append(node)
                    queue.append(node.id)
                    
                    if len(lookahead) >= count:
                        break
        
        return lookahead


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_graph_service(db: AsyncSession) -> GraphService:
    """Factory function for dependency injection."""
    return GraphService(db)
