"""
Proactive Companion System

Makes Lyo reach out first at the right moments:
- Time-based interventions (morning rituals, evening reflections)
- Event-based interventions (streaks, milestones)
- Smart notification timing
"""

from .intervention_engine import intervention_engine
from .models import Intervention, InterventionLog, UserNotificationPreferences

__all__ = ['intervention_engine', 'Intervention', 'InterventionLog', 'UserNotificationPreferences']
