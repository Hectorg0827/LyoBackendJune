"""Lyo Coach — goal-aware orchestration over the canonical Learning OS.

The coach does not own a second learner model.  It reads the immutable learning
event/evidence stream and the canonical concept graph, then derives goals,
readiness and the next best learning action.  Test Prep is one adapter into the
same goal model rather than a separate AI.
"""

from .models import CoachSnapshot, GoalSkill, LearningGoal

__all__ = ["LearningGoal", "GoalSkill", "CoachSnapshot"]
