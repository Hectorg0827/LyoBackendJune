"""
Gamification module for the LyoApp backend.

This module provides gamification features including:
- Experience points (XP) and user levels
- Achievement system with badges
- Streak tracking for user engagement
- Leaderboards for competitive elements
- Statistical insights and analytics
"""

from lyo_app.gamification.service import GamificationService

__all__ = ["GamificationService"]
