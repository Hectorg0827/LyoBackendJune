"""Shared deterministic teaching runtime used by Chat and Classroom.

Models provide language; the runtime owns state transitions and the pedagogical
policy. LLMs may realise a chosen action, but they do not get to invent
mastery, completion, or session state.
"""

from .models import (
    LearnerSnapshot,
    PrerequisiteGap,
    SessionSnapshot,
    TeachingAction,
    TeachingContext,
    TeachingDecision,
    TeachingSurface,
)
from .policy import POLICY_VERSION, TeachingPolicy, canonical_action_for_classroom_move
from .service import decide_for_chat, record_policy_decision

__all__ = [
    "LearnerSnapshot",
    "PrerequisiteGap",
    "SessionSnapshot",
    "TeachingAction",
    "TeachingContext",
    "TeachingDecision",
    "TeachingSurface",
    "POLICY_VERSION",
    "TeachingPolicy",
    "canonical_action_for_classroom_move",
    "bounded_intervention_metadata",
    "record_policy_outcome",
    "teaching_policy_decisions",
    "teaching_policy_outcomes",
    "decide_for_chat",
    "record_policy_decision",
]
