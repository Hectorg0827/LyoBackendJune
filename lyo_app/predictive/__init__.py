"""
Predictive Intelligence System - Phase 2

Anticipates user struggles, dropout risk, and optimal engagement times.
Transforms Lyo from reactive to truly predictive.
"""

from .struggle_predictor import struggle_predictor
from .dropout_prevention import dropout_predictor
from .optimal_timing import timing_optimizer
from .models import (
    StrugglePrediction,
    DropoutRiskScore,
    UserTimingProfile,
    LearningPlateau,
    SkillRegression
)

__all__ = [
    'struggle_predictor',
    'dropout_predictor',
    'timing_optimizer',
    'StrugglePrediction',
    'DropoutRiskScore',
    'UserTimingProfile',
    'LearningPlateau',
    'SkillRegression'
]
