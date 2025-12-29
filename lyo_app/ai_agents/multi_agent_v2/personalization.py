"""
Personalization engine for adaptive course generation based on user history.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UserPreferences:
    """User learning preferences and history"""
    user_id: str
    
    # Learning style
    preferred_teaching_style: str = "balanced"  # "concise", "detailed", "balanced"
    code_verbosity: str = "moderate"  # "minimal", "moderate", "verbose"
    quiz_difficulty: str = "adaptive"  # "easy", "moderate", "hard", "adaptive"
    
    # Personalization data
    favorite_topics: List[str] = field(default_factory=list)
    completed_courses: List[str] = field(default_factory=list)
    average_lesson_time_minutes: Optional[float] = None
    preferred_lesson_length: str = "medium"  # "short", "medium", "long"
    
    # Performance tracking
    average_quiz_score: Optional[float] = None
    strong_areas: List[str] = field(default_factory=list)
    weak_areas: List[str] = field(default_factory=list)
    
    # Updated timestamp
    last_updated: datetime = field(default_factory=datetime.utcnow)


class PersonalizationEngine:
    """
    Adapt course generation based on user's learning history and preferences.
    """
    
    def __init__(self):
        # In production, this would connect to database
        self._preferences_cache: Dict[str, UserPreferences] = {}
    
    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences, create default if not exists"""
        if user_id not in self._preferences_cache:
            # In production: load from database
            self._preferences_cache[user_id] = UserPreferences(user_id=user_id)
        
        return self._preferences_cache[user_id]
    
    async def update_preferences(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> UserPreferences:
        """Update user preferences"""
        prefs = await self.get_preferences(user_id)
        
        for key, value in updates.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        
        prefs.last_updated = datetime.utcnow()
        
        # In production: save to database
        return prefs
    
    async def personalize_generation_config(
        self,
        user_id: str,
        base_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Modify generation config based on user preferences.
        
        Returns:
            Personalized config dictionary
        """
        prefs = await self.get_preferences(user_id)
        config = base_config.copy()
        
        # Adjust based on teaching style preference
        if prefs.preferred_teaching_style == "concise":
            config["enable_multimedia_suggestions"] = False
            config["content_density"] = "high"
        elif prefs.preferred_teaching_style == "detailed":
            config["enable_multimedia_suggestions"] = True
            config["enable_practice_exercises"] = True
            config["content_density"] = "comprehensive"
        
        # Adjust code examples based on preference
        if prefs.code_verbosity == "minimal":
            config["code_example_style"] = "compact"
        elif prefs.code_verbosity == "verbose":
            config["code_example_style"] = "detailed_with_comments"
        
        # Adjust quiz difficulty
        if prefs.average_quiz_score and prefs.quiz_difficulty == "adaptive":
            if prefs.average_quiz_score > 85:
                config["quiz_difficulty"] = "hard"
            elif prefs.average_quiz_score < 60:
                config["quiz_difficulty"] = "easy"
        else:
            config["quiz_difficulty"] = prefs.quiz_difficulty
        
        # Adjust lesson length
        if prefs.preferred_lesson_length == "short":
            config["target_lesson_minutes"] = 10
        elif prefs.preferred_lesson_length == "long":
            config["target_lesson_minutes"] = 30
        else:
            config["target_lesson_minutes"] = 20
        
        return config
    
    async def get_recommendation_context(self, user_id: str) -> Dict[str, Any]:
        """
        Get context for AI to personalize content.
        
        This is injected into the orchestrator prompt.
        """
        prefs = await self.get_preferences(user_id)
        
        context = {
            "teaching_style": prefs.preferred_teaching_style,
            "experience_level": self._infer_experience_level(prefs),
            "learning_pace": self._infer_learning_pace(prefs)
        }
        
        if prefs.completed_courses:
            context["completed_topics"] = prefs.completed_courses[:5]
        
        if prefs.strong_areas:
            context["strong_areas"] = prefs.strong_areas
        
        if prefs.weak_areas:
            context["needs_reinforcement"] = prefs.weak_areas
        
        return context
    
    def _infer_experience_level(self, prefs: UserPreferences) -> str:
        """Infer overall experience level from history"""
        if not prefs.completed_courses:
            return "beginner"
        
        course_count = len(prefs.completed_courses)
        avg_score = prefs.average_quiz_score or 70
        
        if course_count >= 10 and avg_score >= 80:
            return "advanced"
        elif course_count >= 5 or avg_score >= 75:
            return "intermediate"
        else:
            return "beginner"
    
    def _infer_learning_pace(self, prefs: UserPreferences) -> str:
        """Infer learning pace from completion data"""
        if not prefs.average_lesson_time_minutes:
            return "moderate"
        
        # These are example thresholds
        if prefs.average_lesson_time_minutes < 15:
            return "fast"
        elif prefs.average_lesson_time_minutes > 30:
            return "thorough"
        else:
            return "moderate"


# Global instance
_personalization_engine: Optional[PersonalizationEngine] = None


def get_personalization_engine() -> PersonalizationEngine:
    """Get or create global personalization engine"""
    global _personalization_engine
    
    if _personalization_engine is None:
        _personalization_engine = PersonalizationEngine()
    
    return _personalization_engine
