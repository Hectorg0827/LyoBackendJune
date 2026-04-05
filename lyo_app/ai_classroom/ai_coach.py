"""
Living Classroom - AI Coach System
=================================

Advanced AI coaching system that provides personalized learning guidance,
emotional support, and adaptive teaching strategies in real-time.

Features:
- Emotional intelligence and empathy
- Personalized learning path optimization
- Real-time difficulty adjustment
- Motivational coaching
- Learning style adaptation
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .sdui_models import (
    Scene, SceneType, Component, ComponentType,
    TeacherMessage, StudentPrompt, QuizCard, CTAButton, Celebration,
    ActionIntent, AudioMood
)

logger = logging.getLogger(__name__)


class LearningStyle(str, Enum):
    """Learning style preferences"""
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING = "reading"
    MIXED = "mixed"


class EmotionalState(str, Enum):
    """Student emotional states"""
    CONFIDENT = "confident"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    EXCITED = "excited"
    BORED = "bored"
    ANXIOUS = "anxious"
    MOTIVATED = "motivated"
    OVERWHELMED = "overwhelmed"


class CoachingStrategy(str, Enum):
    """AI coaching strategies"""
    ENCOURAGING = "encouraging"
    CHALLENGING = "challenging"
    SUPPORTIVE = "supportive"
    EXPLANATORY = "explanatory"
    MOTIVATIONAL = "motivational"
    PATIENT = "patient"
    ENERGETIC = "energetic"


@dataclass
class StudentProfile:
    """Comprehensive student profile for AI coaching"""
    user_id: str
    learning_style: LearningStyle = LearningStyle.MIXED
    current_emotional_state: EmotionalState = EmotionalState.MOTIVATED

    # Learning preferences
    preferred_pace: str = "medium"  # slow, medium, fast
    difficulty_preference: str = "adaptive"  # easy, medium, hard, adaptive
    feedback_style: str = "immediate"  # immediate, summary, minimal

    # Performance tracking
    mastery_levels: Dict[str, float] = field(default_factory=dict)  # concept -> mastery (0-1)
    recent_performance: List[float] = field(default_factory=list)  # Recent scores
    struggle_areas: List[str] = field(default_factory=list)
    strength_areas: List[str] = field(default_factory=list)

    # Engagement metrics
    session_duration_minutes: float = 0.0
    questions_asked: int = 0
    hints_requested: int = 0
    mistakes_made: int = 0
    breakthroughs_achieved: int = 0

    # Personalization data
    preferred_examples: List[str] = field(default_factory=list)  # Types of examples that work
    effective_analogies: List[str] = field(default_factory=list)
    motivation_triggers: List[str] = field(default_factory=list)

    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CoachingRecommendation:
    """AI coaching recommendation"""
    strategy: CoachingStrategy
    confidence: float  # 0-1
    reasoning: str
    suggested_components: List[str]
    emotional_tone: str
    difficulty_adjustment: float  # -1 to 1 (easier to harder)
    personalization_data: Dict[str, Any] = field(default_factory=dict)


class AICoach:
    """Advanced AI coaching system with emotional intelligence"""

    def __init__(self):
        self.student_profiles: Dict[str, StudentProfile] = {}
        self.coaching_history: Dict[str, List[CoachingRecommendation]] = {}

        # Learning analytics
        self.concept_difficulty_map = self._load_concept_difficulty_map()
        self.emotional_transition_patterns = self._load_emotional_patterns()

        logger.info("🧠 AI Coach System initialized with emotional intelligence")

    def _load_concept_difficulty_map(self) -> Dict[str, float]:
        """Load concept difficulty mapping (0-1 scale)"""
        return {
            # Programming concepts
            "variables": 0.2,
            "functions": 0.4,
            "loops": 0.6,
            "recursion": 0.9,
            "data_structures": 0.7,
            "algorithms": 0.8,

            # Math concepts
            "arithmetic": 0.1,
            "algebra": 0.5,
            "calculus": 0.8,
            "statistics": 0.6,

            # General difficulty fallback
            "default": 0.5
        }

    def _load_emotional_patterns(self) -> Dict[EmotionalState, Dict[str, Any]]:
        """Load emotional state transition patterns"""
        return {
            EmotionalState.FRUSTRATED: {
                "triggers": ["multiple_wrong_answers", "complex_concept", "time_pressure"],
                "coaching_strategies": [CoachingStrategy.SUPPORTIVE, CoachingStrategy.PATIENT],
                "recommended_actions": ["break_down_concept", "provide_encouragement", "reduce_difficulty"],
                "avoid": ["challenging_questions", "time_pressure"]
            },
            EmotionalState.CONFIDENT: {
                "triggers": ["correct_answers", "quick_understanding", "positive_feedback"],
                "coaching_strategies": [CoachingStrategy.CHALLENGING, CoachingStrategy.MOTIVATIONAL],
                "recommended_actions": ["increase_difficulty", "introduce_extensions"],
                "avoid": ["overly_simple_content"]
            },
            EmotionalState.CONFUSED: {
                "triggers": ["complex_explanation", "abstract_concepts", "missing_prerequisites"],
                "coaching_strategies": [CoachingStrategy.EXPLANATORY, CoachingStrategy.PATIENT],
                "recommended_actions": ["simplify_explanation", "use_analogies", "check_prerequisites"],
                "avoid": ["rushing", "multiple_concepts_at_once"]
            },
            EmotionalState.BORED: {
                "triggers": ["repetitive_content", "too_easy", "long_sessions"],
                "coaching_strategies": [CoachingStrategy.ENERGETIC, CoachingStrategy.CHALLENGING],
                "recommended_actions": ["increase_difficulty", "add_variety", "gamification"],
                "avoid": ["repetition", "slow_pace"]
            }
        }

    async def analyze_student_state(self,
                                   user_id: str,
                                   session_data: Dict[str, Any],
                                   recent_interactions: List[Dict[str, Any]]) -> StudentProfile:
        """Analyze current student state using AI"""

        # Get or create student profile
        if user_id not in self.student_profiles:
            self.student_profiles[user_id] = StudentProfile(user_id=user_id)

        profile = self.student_profiles[user_id]

        # Update emotional state based on recent interactions
        profile.current_emotional_state = await self._detect_emotional_state(recent_interactions)

        # Update performance metrics
        await self._update_performance_metrics(profile, session_data, recent_interactions)

        # Update learning style detection
        profile.learning_style = await self._detect_learning_style(profile, recent_interactions)

        # Identify struggle and strength areas
        await self._update_learning_areas(profile, recent_interactions)

        profile.last_updated = datetime.utcnow()
        return profile

    async def generate_coaching_recommendation(self,
                                             user_id: str,
                                             current_scene_type: SceneType,
                                             context: Dict[str, Any]) -> CoachingRecommendation:
        """Generate AI coaching recommendation based on student state"""

        if user_id not in self.student_profiles:
            # Create basic profile for new user
            self.student_profiles[user_id] = StudentProfile(user_id=user_id)

        profile = self.student_profiles[user_id]

        # Analyze current situation
        situation_analysis = await self._analyze_learning_situation(profile, current_scene_type, context)

        # Select optimal coaching strategy
        strategy = await self._select_coaching_strategy(profile, situation_analysis)

        # Generate specific recommendations
        recommendation = CoachingRecommendation(
            strategy=strategy,
            confidence=situation_analysis["confidence"],
            reasoning=situation_analysis["reasoning"],
            suggested_components=await self._suggest_components(profile, strategy, context),
            emotional_tone=await self._select_emotional_tone(profile, strategy),
            difficulty_adjustment=await self._calculate_difficulty_adjustment(profile, context),
            personalization_data=await self._generate_personalization_data(profile, context)
        )

        # Store in history
        if user_id not in self.coaching_history:
            self.coaching_history[user_id] = []
        self.coaching_history[user_id].append(recommendation)

        return recommendation

    async def enhance_scene_with_coaching(self,
                                        scene: Scene,
                                        user_id: str,
                                        coaching_recommendation: CoachingRecommendation) -> Scene:
        """Enhance scene with AI coaching elements"""

        enhanced_components = []

        # Add coaching-enhanced components
        for component in scene.components:
            enhanced_component = await self._enhance_component_with_coaching(
                component, coaching_recommendation
            )
            enhanced_components.append(enhanced_component)

        # Add additional coaching components if needed
        coaching_components = await self._generate_coaching_components(
            user_id, coaching_recommendation, scene.scene_type
        )
        enhanced_components.extend(coaching_components)

        # Sort by priority (coaching components get appropriate priority)
        enhanced_components.sort(key=lambda c: c.priority)

        # Create enhanced scene
        enhanced_scene = Scene(
            scene_type=scene.scene_type,
            components=enhanced_components,
            priority=scene.priority,
            metadata=scene.metadata
        )

        return enhanced_scene

    async def _detect_emotional_state(self, recent_interactions: List[Dict[str, Any]]) -> EmotionalState:
        """Detect student's current emotional state from interactions"""

        if not recent_interactions:
            return EmotionalState.MOTIVATED

        # Analyze patterns in recent interactions
        wrong_answers = sum(1 for i in recent_interactions if not i.get("is_correct", True))
        hint_requests = sum(1 for i in recent_interactions if i.get("action_type") == "request_hint")
        time_spent = sum(i.get("time_spent_ms", 0) for i in recent_interactions) / 1000.0  # seconds

        # Simple emotional state detection logic
        if wrong_answers >= 3:
            if hint_requests > 1:
                return EmotionalState.FRUSTRATED
            else:
                return EmotionalState.CONFUSED
        elif wrong_answers == 0 and len(recent_interactions) > 2:
            if time_spent < 30:  # Very quick answers
                return EmotionalState.CONFIDENT
            else:
                return EmotionalState.MOTIVATED
        elif time_spent > 300:  # 5+ minutes on recent interactions
            return EmotionalState.OVERWHELMED
        else:
            return EmotionalState.MOTIVATED

    async def _update_performance_metrics(self,
                                        profile: StudentProfile,
                                        session_data: Dict[str, Any],
                                        recent_interactions: List[Dict[str, Any]]):
        """Update student performance metrics"""

        # Update recent performance
        recent_scores = [
            1.0 if i.get("is_correct", True) else 0.0
            for i in recent_interactions
            if "is_correct" in i
        ]

        profile.recent_performance.extend(recent_scores)
        # Keep only last 20 scores
        profile.recent_performance = profile.recent_performance[-20:]

        # Update engagement metrics
        profile.session_duration_minutes = session_data.get("duration_minutes", 0.0)
        profile.questions_asked += session_data.get("questions_asked", 0)
        profile.hints_requested += sum(1 for i in recent_interactions if i.get("action_type") == "request_hint")
        profile.mistakes_made += sum(1 for i in recent_interactions if not i.get("is_correct", True))

    async def _detect_learning_style(self,
                                   profile: StudentProfile,
                                   recent_interactions: List[Dict[str, Any]]) -> LearningStyle:
        """Detect student's preferred learning style"""

        # Analyze interaction patterns to infer learning style
        # This is a simplified version - production would use more sophisticated analysis

        visual_indicators = 0
        auditory_indicators = 0
        kinesthetic_indicators = 0

        for interaction in recent_interactions:
            # Visual learners tend to spend more time reading
            if interaction.get("time_spent_ms", 0) > 30000:  # 30+ seconds
                visual_indicators += 1

            # Auditory learners might request audio features more
            if interaction.get("requested_audio", False):
                auditory_indicators += 1

            # Kinesthetic learners might interact more with interactive elements
            if interaction.get("interaction_count", 0) > 3:
                kinesthetic_indicators += 1

        # Determine dominant style
        max_indicators = max(visual_indicators, auditory_indicators, kinesthetic_indicators)
        if max_indicators == 0:
            return LearningStyle.MIXED
        elif visual_indicators == max_indicators:
            return LearningStyle.VISUAL
        elif auditory_indicators == max_indicators:
            return LearningStyle.AUDITORY
        else:
            return LearningStyle.KINESTHETIC

    async def _update_learning_areas(self, profile: StudentProfile, recent_interactions: List[Dict[str, Any]]):
        """Update student's struggle and strength areas"""

        concept_performance = {}

        for interaction in recent_interactions:
            concept = interaction.get("concept", "general")
            is_correct = interaction.get("is_correct", True)

            if concept not in concept_performance:
                concept_performance[concept] = []
            concept_performance[concept].append(is_correct)

        # Update struggle and strength areas
        profile.struggle_areas = []
        profile.strength_areas = []

        for concept, performances in concept_performance.items():
            accuracy = sum(performances) / len(performances)

            if accuracy < 0.5:
                profile.struggle_areas.append(concept)
            elif accuracy > 0.8:
                profile.strength_areas.append(concept)

    async def _analyze_learning_situation(self,
                                        profile: StudentProfile,
                                        scene_type: SceneType,
                                        context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current learning situation"""

        # Analyze context factors
        current_concept = context.get("concept", "general")
        difficulty_level = self.concept_difficulty_map.get(current_concept, 0.5)
        user_mastery = profile.mastery_levels.get(current_concept, 0.0)

        # Calculate difficulty gap
        difficulty_gap = difficulty_level - user_mastery

        # Analyze recent performance trend
        recent_avg = (
            sum(profile.recent_performance[-5:]) / len(profile.recent_performance[-5:])
            if profile.recent_performance else 0.5
        )

        # Generate situation analysis
        analysis = {
            "confidence": 0.8,  # Default confidence
            "reasoning": "",
            "factors": {
                "emotional_state": profile.current_emotional_state.value,
                "difficulty_gap": difficulty_gap,
                "recent_performance": recent_avg,
                "scene_type": scene_type.value
            }
        }

        # Generate reasoning
        if difficulty_gap > 0.3:
            analysis["reasoning"] = f"Concept difficulty ({difficulty_level:.1f}) significantly exceeds mastery ({user_mastery:.1f}). Student may need additional support."
        elif difficulty_gap < -0.2:
            analysis["reasoning"] = f"Student mastery ({user_mastery:.1f}) exceeds concept difficulty ({difficulty_level:.1f}). Ready for challenges."
        else:
            analysis["reasoning"] = "Difficulty level appropriate for current mastery. Proceed with adaptive support."

        return analysis

    async def _select_coaching_strategy(self,
                                      profile: StudentProfile,
                                      situation_analysis: Dict[str, Any]) -> CoachingStrategy:
        """Select optimal coaching strategy"""

        emotional_state = profile.current_emotional_state
        difficulty_gap = situation_analysis["factors"]["difficulty_gap"]
        recent_performance = situation_analysis["factors"]["recent_performance"]

        # Strategy selection logic based on emotional patterns
        if emotional_state in self.emotional_transition_patterns:
            recommended_strategies = self.emotional_transition_patterns[emotional_state]["coaching_strategies"]

            # Select best strategy based on situation
            if difficulty_gap > 0.2 and recent_performance < 0.6:
                # Student struggling - use supportive strategies
                supportive_strategies = [s for s in recommended_strategies if s in [CoachingStrategy.SUPPORTIVE, CoachingStrategy.PATIENT]]
                return supportive_strategies[0] if supportive_strategies else CoachingStrategy.SUPPORTIVE
            elif recent_performance > 0.8:
                # Student doing well - use challenging strategies
                challenging_strategies = [s for s in recommended_strategies if s in [CoachingStrategy.CHALLENGING, CoachingStrategy.MOTIVATIONAL]]
                return challenging_strategies[0] if challenging_strategies else CoachingStrategy.ENCOURAGING
            else:
                # Default to first recommended strategy
                return recommended_strategies[0]

        # Fallback strategy selection
        if recent_performance < 0.5:
            return CoachingStrategy.SUPPORTIVE
        elif recent_performance > 0.8:
            return CoachingStrategy.CHALLENGING
        else:
            return CoachingStrategy.ENCOURAGING

    async def _suggest_components(self,
                                profile: StudentProfile,
                                strategy: CoachingStrategy,
                                context: Dict[str, Any]) -> List[str]:
        """Suggest specific components based on coaching strategy"""

        components = []

        if strategy == CoachingStrategy.SUPPORTIVE:
            components.extend(["TeacherMessage", "StudentPrompt"])
        elif strategy == CoachingStrategy.CHALLENGING:
            components.extend(["QuizCard", "CTAButton"])
        elif strategy == CoachingStrategy.ENCOURAGING:
            components.extend(["TeacherMessage", "Celebration"])
        elif strategy == CoachingStrategy.MOTIVATIONAL:
            components.extend(["Celebration", "CTAButton"])
        elif strategy == CoachingStrategy.EXPLANATORY:
            components.extend(["TeacherMessage"])

        # Add learning style specific components
        if profile.learning_style == LearningStyle.VISUAL:
            components.append("VisualAid")  # Would be implemented
        elif profile.learning_style == LearningStyle.AUDITORY:
            components.append("AudioExplanation")  # Would be implemented

        return components

    async def _select_emotional_tone(self, profile: StudentProfile, strategy: CoachingStrategy) -> str:
        """Select appropriate emotional tone"""

        emotional_state = profile.current_emotional_state

        tone_mapping = {
            (EmotionalState.FRUSTRATED, CoachingStrategy.SUPPORTIVE): "calm_reassuring",
            (EmotionalState.CONFIDENT, CoachingStrategy.CHALLENGING): "excited_challenging",
            (EmotionalState.CONFUSED, CoachingStrategy.EXPLANATORY): "patient_clear",
            (EmotionalState.BORED, CoachingStrategy.ENERGETIC): "enthusiastic",
            (EmotionalState.ANXIOUS, CoachingStrategy.PATIENT): "gentle_encouraging"
        }

        return tone_mapping.get((emotional_state, strategy), "encouraging")

    async def _calculate_difficulty_adjustment(self,
                                             profile: StudentProfile,
                                             context: Dict[str, Any]) -> float:
        """Calculate difficulty adjustment (-1 to 1)"""

        recent_avg = (
            sum(profile.recent_performance[-5:]) / len(profile.recent_performance[-5:])
            if profile.recent_performance else 0.5
        )

        # Adjust difficulty based on performance
        if recent_avg < 0.4:
            return -0.3  # Make easier
        elif recent_avg > 0.9:
            return 0.2   # Make harder
        else:
            return 0.0   # Keep same

    async def _generate_personalization_data(self,
                                           profile: StudentProfile,
                                           context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate personalization data for components"""

        return {
            "learning_style": profile.learning_style.value,
            "emotional_state": profile.current_emotional_state.value,
            "preferred_examples": profile.preferred_examples,
            "effective_analogies": profile.effective_analogies,
            "mastery_level": profile.mastery_levels.get(context.get("concept", "general"), 0.0),
            "recent_performance": profile.recent_performance[-3:] if profile.recent_performance else []
        }

    async def _enhance_component_with_coaching(self,
                                             component: Component,
                                             recommendation: CoachingRecommendation) -> Component:
        """Enhance component with coaching intelligence"""

        # Modify component based on coaching recommendation
        if hasattr(component, 'emotion') and component.type == "TeacherMessage":
            # Adjust emotional tone
            component.emotion = recommendation.emotional_tone

            # Adjust audio mood if available
            if hasattr(component, 'audio_mood'):
                component.audio_mood = self._map_tone_to_audio_mood(recommendation.emotional_tone)

        # Adjust component priority based on coaching strategy
        if recommendation.strategy == CoachingStrategy.CHALLENGING:
            component.priority = max(1, component.priority - 1)  # Higher priority
        elif recommendation.strategy == CoachingStrategy.PATIENT:
            component.priority = component.priority + 1  # Lower priority

        return component

    async def _generate_coaching_components(self,
                                          user_id: str,
                                          recommendation: CoachingRecommendation,
                                          scene_type: SceneType) -> List[Component]:
        """Generate additional coaching-specific components"""

        coaching_components = []

        # Add AI peer interaction for emotional support
        if recommendation.strategy == CoachingStrategy.SUPPORTIVE and scene_type == SceneType.CORRECTION:
            peer_component = StudentPrompt(
                student_name="Alex",
                text=self._generate_supportive_peer_message(recommendation),
                purpose="emotional_support",
                priority=2
            )
            coaching_components.append(peer_component)

        # Add motivational celebration for confidence building
        if recommendation.strategy == CoachingStrategy.MOTIVATIONAL:
            celebration_component = Celebration(
                message=self._generate_motivational_message(recommendation),
                celebration_type="achievement",
                particle_effect=True,
                priority=1
            )
            coaching_components.append(celebration_component)

        # Add personalized teacher guidance
        if "TeacherMessage" in recommendation.suggested_components:
            teacher_message = TeacherMessage(
                text=self._generate_coaching_message(recommendation),
                emotion=recommendation.emotional_tone,
                audio_mood=self._map_tone_to_audio_mood(recommendation.emotional_tone),
                priority=1
            )
            coaching_components.append(teacher_message)

        return coaching_components

    def _map_tone_to_audio_mood(self, emotional_tone: str) -> AudioMood:
        """Map emotional tone to audio mood"""

        tone_mapping = {
            "calm_reassuring": AudioMood.GENTLE,
            "excited_challenging": AudioMood.ENERGETIC,
            "patient_clear": AudioMood.CALM,
            "enthusiastic": AudioMood.ENERGETIC,
            "gentle_encouraging": AudioMood.GENTLE
        }

        return tone_mapping.get(emotional_tone, AudioMood.CALM)

    def _generate_supportive_peer_message(self, recommendation: CoachingRecommendation) -> str:
        """Generate supportive peer message"""

        messages = [
            "I found this tricky at first too! Don't worry, it gets easier with practice.",
            "This concept took me a while to understand as well. You're not alone!",
            "I made the same mistake when I was learning this. Keep going!",
            "Everyone learns at their own pace. You're doing great!"
        ]

        # Simple selection based on hash for consistency
        message_index = hash(recommendation.reasoning) % len(messages)
        return messages[message_index]

    def _generate_motivational_message(self, recommendation: CoachingRecommendation) -> str:
        """Generate motivational celebration message"""

        messages = [
            "Fantastic work! You're really getting the hang of this! 🌟",
            "Excellent! Your understanding is growing stronger! ✨",
            "Amazing progress! Keep up this great momentum! 🚀",
            "Outstanding! You should be proud of your learning! 🎯"
        ]

        message_index = hash(recommendation.reasoning) % len(messages)
        return messages[message_index]

    def _generate_coaching_message(self, recommendation: CoachingRecommendation) -> str:
        """Generate personalized coaching message"""

        strategy = recommendation.strategy

        if strategy == CoachingStrategy.SUPPORTIVE:
            return "I can see you're working hard on this. Let's break it down into smaller steps that will be easier to understand."
        elif strategy == CoachingStrategy.CHALLENGING:
            return "You're doing really well! I think you're ready to tackle something a bit more advanced. Let's see what you can do!"
        elif strategy == CoachingStrategy.ENCOURAGING:
            return "You're making great progress! Your effort is really paying off. Keep up the excellent work!"
        elif strategy == CoachingStrategy.EXPLANATORY:
            return "Let me explain this concept in a different way that might make it clearer for you."
        elif strategy == CoachingStrategy.MOTIVATIONAL:
            return "Your dedication to learning is impressive! Every challenge you overcome makes you stronger!"
        elif strategy == CoachingStrategy.PATIENT:
            return "Learning takes time, and that's perfectly okay. We'll go at whatever pace works best for you."
        else:
            return "I'm here to help you succeed. Let's work through this together!"

    def get_coaching_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive coaching analytics for user"""

        if user_id not in self.student_profiles:
            return {"error": "No coaching data available for user"}

        profile = self.student_profiles[user_id]
        history = self.coaching_history.get(user_id, [])

        return {
            "student_profile": {
                "learning_style": profile.learning_style.value,
                "emotional_state": profile.current_emotional_state.value,
                "mastery_levels": profile.mastery_levels,
                "performance_trend": profile.recent_performance[-10:] if profile.recent_performance else [],
                "engagement_metrics": {
                    "session_duration_minutes": profile.session_duration_minutes,
                    "questions_asked": profile.questions_asked,
                    "hints_requested": profile.hints_requested,
                    "breakthroughs_achieved": profile.breakthroughs_achieved
                }
            },
            "coaching_history": {
                "total_recommendations": len(history),
                "strategy_distribution": self._calculate_strategy_distribution(history),
                "recent_strategies": [r.strategy.value for r in history[-5:]]
            },
            "learning_insights": {
                "struggle_areas": profile.struggle_areas,
                "strength_areas": profile.strength_areas,
                "preferred_examples": profile.preferred_examples,
                "effective_analogies": profile.effective_analogies
            }
        }

    def _calculate_strategy_distribution(self, history: List[CoachingRecommendation]) -> Dict[str, int]:
        """Calculate distribution of coaching strategies used"""

        distribution = {}
        for recommendation in history:
            strategy = recommendation.strategy.value
            distribution[strategy] = distribution.get(strategy, 0) + 1

        return distribution


# Global AI coach instance
_ai_coach: Optional[AICoach] = None


async def get_ai_coach() -> AICoach:
    """Get AI coach instance"""
    global _ai_coach

    if _ai_coach is None:
        _ai_coach = AICoach()

    return _ai_coach


# Convenience functions
async def get_coaching_recommendation(user_id: str,
                                    scene_type: SceneType,
                                    context: Dict[str, Any],
                                    recent_interactions: List[Dict[str, Any]]) -> CoachingRecommendation:
    """Get AI coaching recommendation for user"""
    coach = await get_ai_coach()

    # Update student analysis
    await coach.analyze_student_state(user_id, context, recent_interactions)

    # Generate recommendation
    return await coach.generate_coaching_recommendation(user_id, scene_type, context)


async def enhance_scene_with_ai_coaching(scene: Scene,
                                       user_id: str,
                                       context: Dict[str, Any],
                                       recent_interactions: List[Dict[str, Any]]) -> Scene:
    """Enhance scene with AI coaching intelligence"""
    coach = await get_ai_coach()

    # Get coaching recommendation
    recommendation = await get_coaching_recommendation(user_id, scene.scene_type, context, recent_interactions)

    # Enhance scene
    return await coach.enhance_scene_with_coaching(scene, user_id, recommendation)