"""
Adaptive Learning Engine for AI Classroom
Personalizes learning experience based on user performance and behavior patterns
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging
import statistics
from pydantic import BaseModel, Field
from .realtime_sync import SyncEvent, SyncEventType, realtime_sync

logger = logging.getLogger(__name__)

class LearningStyle(str, Enum):
    """Detected learning styles"""
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING_WRITING = "reading_writing"
    MIXED = "mixed"

class DifficultyLevel(str, Enum):
    """Content difficulty levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class AdaptationTrigger(str, Enum):
    """Triggers for adaptive content changes"""
    PERFORMANCE_DROP = "performance_drop"
    CONSISTENT_SUCCESS = "consistent_success"
    TIME_SPENT_EXCESSIVE = "time_spent_excessive"
    TIME_SPENT_MINIMAL = "time_spent_minimal"
    REPEATED_MISTAKES = "repeated_mistakes"
    ENGAGEMENT_DROP = "engagement_drop"
    LEARNING_PLATEAU = "learning_plateau"

class LearnerProfile(BaseModel):
    """Comprehensive learner profile"""
    user_id: str
    learning_style: LearningStyle = LearningStyle.MIXED
    preferred_pace: float = 1.0  # 1.0 = normal, <1.0 = slower, >1.0 = faster
    difficulty_preference: DifficultyLevel = DifficultyLevel.INTERMEDIATE
    attention_span: int = 25  # minutes
    optimal_session_length: int = 45  # minutes
    best_performance_time: Optional[str] = None  # hour of day
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    confidence_score: float = 0.5  # 0.0-1.0
    engagement_score: float = 0.5  # 0.0-1.0
    last_updated: datetime = Field(default_factory=datetime.now)

class PerformanceMetrics(BaseModel):
    """Performance tracking metrics"""
    user_id: str
    course_id: str
    lesson_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    completion_rate: float = 0.0  # 0.0-1.0
    accuracy_rate: float = 0.0  # 0.0-1.0
    time_spent_minutes: float = 0.0
    attempts_count: int = 1
    help_requests: int = 0
    engagement_events: List[str] = Field(default_factory=list)
    mistakes: List[Dict[str, Any]] = Field(default_factory=list)

class AdaptiveRecommendation(BaseModel):
    """Adaptive learning recommendation"""
    user_id: str
    recommendation_id: str
    trigger: AdaptationTrigger
    recommendation_type: str  # content, pacing, difficulty, style
    priority: int = 1  # 1=high, 2=medium, 3=low
    title: str
    description: str
    action_data: Dict[str, Any]
    expires_at: Optional[datetime] = None
    implemented: bool = False

class AdaptiveLearningEngine:
    """Intelligent adaptive learning system"""

    def __init__(self):
        self.learner_profiles: Dict[str, LearnerProfile] = {}
        self.performance_history: Dict[str, List[PerformanceMetrics]] = {}
        self.active_recommendations: Dict[str, List[AdaptiveRecommendation]] = {}
        self.adaptation_rules: Dict[AdaptationTrigger, List[callable]] = {}
        self.learning_analytics: Dict[str, Any] = {}

        # Initialize adaptation rules
        self._setup_adaptation_rules()

        # Register with real-time sync
        realtime_sync.register_event_handler(SyncEventType.PROGRESS_UPDATE, self._handle_progress_update)
        realtime_sync.register_event_handler(SyncEventType.LESSON_COMPLETE, self._handle_lesson_completion)
        realtime_sync.register_event_handler(SyncEventType.QUIZ_SUBMIT, self._handle_quiz_submission)

    def _setup_adaptation_rules(self):
        """Setup adaptive learning rules"""
        self.adaptation_rules = {
            AdaptationTrigger.PERFORMANCE_DROP: [
                self._suggest_review_content,
                self._suggest_easier_difficulty,
                self._suggest_additional_practice
            ],
            AdaptationTrigger.CONSISTENT_SUCCESS: [
                self._suggest_advanced_content,
                self._suggest_faster_pace,
                self._suggest_challenge_activities
            ],
            AdaptationTrigger.TIME_SPENT_EXCESSIVE: [
                self._suggest_break,
                self._suggest_different_approach,
                self._suggest_simpler_explanation
            ],
            AdaptationTrigger.REPEATED_MISTAKES: [
                self._suggest_concept_review,
                self._suggest_alternative_learning_path,
                self._suggest_one_on_one_help
            ],
            AdaptationTrigger.ENGAGEMENT_DROP: [
                self._suggest_interactive_content,
                self._suggest_gamification,
                self._suggest_break_or_change_topic
            ]
        }

    async def get_or_create_profile(self, user_id: str) -> LearnerProfile:
        """Get existing learner profile or create new one"""
        if user_id not in self.learner_profiles:
            self.learner_profiles[user_id] = LearnerProfile(user_id=user_id)
            logger.info(f"Created new learner profile for user {user_id}")

        return self.learner_profiles[user_id]

    async def track_performance(self, user_id: str, course_id: str, lesson_id: str,
                              performance_data: Dict[str, Any]) -> PerformanceMetrics:
        """Track and analyze learning performance"""
        metrics = PerformanceMetrics(
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            start_time=datetime.fromisoformat(performance_data.get('start_time', datetime.now().isoformat())),
            end_time=datetime.fromisoformat(performance_data.get('end_time')) if performance_data.get('end_time') else None,
            completion_rate=performance_data.get('completion_rate', 0.0),
            accuracy_rate=performance_data.get('accuracy_rate', 0.0),
            time_spent_minutes=performance_data.get('time_spent_minutes', 0.0),
            attempts_count=performance_data.get('attempts_count', 1),
            help_requests=performance_data.get('help_requests', 0),
            engagement_events=performance_data.get('engagement_events', []),
            mistakes=performance_data.get('mistakes', [])
        )

        # Store performance history
        if user_id not in self.performance_history:
            self.performance_history[user_id] = []
        self.performance_history[user_id].append(metrics)

        # Trigger adaptive analysis
        await self._analyze_and_adapt(user_id, metrics)

        return metrics

    async def _analyze_and_adapt(self, user_id: str, current_metrics: PerformanceMetrics):
        """Analyze performance and generate adaptive recommendations"""
        profile = await self.get_or_create_profile(user_id)
        user_history = self.performance_history.get(user_id, [])

        # Update learner profile based on current performance
        await self._update_learner_profile(profile, current_metrics, user_history)

        # Detect adaptation triggers
        triggers = await self._detect_adaptation_triggers(user_id, current_metrics, user_history)

        # Generate recommendations for each trigger
        for trigger in triggers:
            recommendations = await self._generate_recommendations(user_id, trigger, current_metrics)
            await self._store_and_send_recommendations(user_id, recommendations)

    async def _update_learner_profile(self, profile: LearnerProfile,
                                    current_metrics: PerformanceMetrics,
                                    history: List[PerformanceMetrics]):
        """Update learner profile based on performance data"""
        if not history:
            return

        # Update confidence score
        recent_accuracy = [m.accuracy_rate for m in history[-5:]]  # Last 5 sessions
        if recent_accuracy:
            profile.confidence_score = statistics.mean(recent_accuracy)

        # Update engagement score
        recent_completion = [m.completion_rate for m in history[-5:]]
        if recent_completion:
            profile.engagement_score = statistics.mean(recent_completion)

        # Detect learning style based on performance patterns
        profile.learning_style = await self._detect_learning_style(history)

        # Update optimal session length
        successful_sessions = [m for m in history[-10:] if m.accuracy_rate > 0.7]
        if successful_sessions:
            avg_time = statistics.mean([s.time_spent_minutes for s in successful_sessions])
            profile.optimal_session_length = max(15, min(90, int(avg_time * 1.2)))

        # Update strengths and weaknesses
        await self._update_strengths_weaknesses(profile, history)

        profile.last_updated = datetime.now()
        logger.debug(f"Updated learner profile for {profile.user_id}")

    async def _detect_learning_style(self, history: List[PerformanceMetrics]) -> LearningStyle:
        """Detect learning style based on engagement patterns"""
        # This is a simplified detection - in reality, would analyze interaction patterns
        if not history:
            return LearningStyle.MIXED

        # Analyze engagement events to infer learning style preferences
        visual_events = sum(1 for m in history for e in m.engagement_events if 'image' in e or 'video' in e)
        reading_events = sum(1 for m in history for e in m.engagement_events if 'text' in e or 'read' in e)
        interactive_events = sum(1 for m in history for e in m.engagement_events if 'click' in e or 'interact' in e)

        total_events = visual_events + reading_events + interactive_events
        if total_events == 0:
            return LearningStyle.MIXED

        # Determine dominant style
        if visual_events / total_events > 0.4:
            return LearningStyle.VISUAL
        elif reading_events / total_events > 0.4:
            return LearningStyle.READING_WRITING
        elif interactive_events / total_events > 0.4:
            return LearningStyle.KINESTHETIC
        else:
            return LearningStyle.MIXED

    async def _update_strengths_weaknesses(self, profile: LearnerProfile, history: List[PerformanceMetrics]):
        """Update learner strengths and weaknesses"""
        if len(history) < 3:
            return

        # Analyze mistake patterns to identify weaknesses
        mistake_categories = {}
        for metrics in history[-10:]:  # Last 10 sessions
            for mistake in metrics.mistakes:
                category = mistake.get('category', 'general')
                mistake_categories[category] = mistake_categories.get(category, 0) + 1

        # Identify top weaknesses
        sorted_mistakes = sorted(mistake_categories.items(), key=lambda x: x[1], reverse=True)
        profile.weaknesses = [cat for cat, count in sorted_mistakes[:3] if count > 2]

        # Identify strengths (topics with high accuracy)
        topic_performance = {}
        for metrics in history[-10:]:
            topic = metrics.lesson_id.split('_')[0] if '_' in metrics.lesson_id else 'general'
            if topic not in topic_performance:
                topic_performance[topic] = []
            topic_performance[topic].append(metrics.accuracy_rate)

        # Calculate average performance per topic
        avg_performance = {
            topic: statistics.mean(scores)
            for topic, scores in topic_performance.items()
            if len(scores) >= 2
        }

        # Identify strengths (performance > 0.8)
        profile.strengths = [topic for topic, avg in avg_performance.items() if avg > 0.8][:5]

    async def _detect_adaptation_triggers(self, user_id: str,
                                        current_metrics: PerformanceMetrics,
                                        history: List[PerformanceMetrics]) -> List[AdaptationTrigger]:
        """Detect when adaptive interventions are needed"""
        triggers = []

        if len(history) < 2:
            return triggers

        # Performance drop detection
        recent_accuracy = [m.accuracy_rate for m in history[-3:]]
        if len(recent_accuracy) >= 2 and statistics.mean(recent_accuracy) < 0.5:
            if len(history) >= 3:
                previous_accuracy = [m.accuracy_rate for m in history[-6:-3]]
                if previous_accuracy and statistics.mean(previous_accuracy) - statistics.mean(recent_accuracy) > 0.2:
                    triggers.append(AdaptationTrigger.PERFORMANCE_DROP)

        # Consistent success detection
        if current_metrics.accuracy_rate > 0.9 and len(history) >= 3:
            last_three_accuracy = [m.accuracy_rate for m in history[-3:]]
            if all(acc > 0.85 for acc in last_three_accuracy):
                triggers.append(AdaptationTrigger.CONSISTENT_SUCCESS)

        # Excessive time spent
        profile = self.learner_profiles.get(user_id)
        expected_time = profile.optimal_session_length if profile else 30
        if current_metrics.time_spent_minutes > expected_time * 2:
            triggers.append(AdaptationTrigger.TIME_SPENT_EXCESSIVE)

        # Repeated mistakes detection
        recent_mistakes = []
        for m in history[-5:]:
            recent_mistakes.extend([mistake.get('type') for mistake in m.mistakes])

        mistake_counts = {}
        for mistake in recent_mistakes:
            if mistake:
                mistake_counts[mistake] = mistake_counts.get(mistake, 0) + 1

        if any(count >= 3 for count in mistake_counts.values()):
            triggers.append(AdaptationTrigger.REPEATED_MISTAKES)

        # Engagement drop detection
        recent_completion = [m.completion_rate for m in history[-3:]]
        if len(recent_completion) >= 2 and statistics.mean(recent_completion) < 0.6:
            triggers.append(AdaptationTrigger.ENGAGEMENT_DROP)

        return triggers

    async def _generate_recommendations(self, user_id: str, trigger: AdaptationTrigger,
                                      metrics: PerformanceMetrics) -> List[AdaptiveRecommendation]:
        """Generate adaptive recommendations based on triggers"""
        recommendations = []
        rule_handlers = self.adaptation_rules.get(trigger, [])

        for handler in rule_handlers:
            try:
                rec = await handler(user_id, trigger, metrics)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                logger.error(f"Error in adaptation rule handler: {e}")

        return recommendations

    async def _suggest_review_content(self, user_id: str, trigger: AdaptationTrigger,
                                    metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest reviewing previous content"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"review_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=1,
            title="Review Previous Content",
            description="Your recent performance suggests reviewing previous lessons might help",
            action_data={
                "action": "show_review_content",
                "lesson_id": metrics.lesson_id,
                "focus_areas": [mistake.get('category') for mistake in metrics.mistakes]
            }
        )

    async def _suggest_easier_difficulty(self, user_id: str, trigger: AdaptationTrigger,
                                       metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest reducing difficulty level"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"easier_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="difficulty",
            priority=1,
            title="Try Easier Content",
            description="Let's try some easier exercises to build your confidence",
            action_data={
                "action": "adjust_difficulty",
                "target_difficulty": "easier",
                "lesson_id": metrics.lesson_id
            }
        )

    async def _suggest_additional_practice(self, user_id: str, trigger: AdaptationTrigger,
                                         metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest additional practice exercises"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"practice_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=2,
            title="Extra Practice",
            description="Additional practice exercises to strengthen your understanding",
            action_data={
                "action": "show_practice_exercises",
                "lesson_id": metrics.lesson_id,
                "exercise_count": 5
            }
        )

    async def _suggest_advanced_content(self, user_id: str, trigger: AdaptationTrigger,
                                      metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest more advanced content"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"advanced_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="difficulty",
            priority=1,
            title="Ready for Advanced Content!",
            description="You're doing great! Try some advanced exercises to challenge yourself",
            action_data={
                "action": "adjust_difficulty",
                "target_difficulty": "advanced",
                "lesson_id": metrics.lesson_id
            }
        )

    async def _suggest_faster_pace(self, user_id: str, trigger: AdaptationTrigger,
                                 metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest increasing learning pace"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"faster_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="pacing",
            priority=2,
            title="Speed Things Up",
            description="You might enjoy a faster pace - want to try the accelerated track?",
            action_data={
                "action": "adjust_pace",
                "target_pace": 1.5,
                "lesson_id": metrics.lesson_id
            }
        )

    async def _suggest_challenge_activities(self, user_id: str, trigger: AdaptationTrigger,
                                          metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest challenge activities"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"challenge_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=2,
            title="Challenge Activity",
            description="Ready for a challenge? Try this special project!",
            action_data={
                "action": "show_challenge_activity",
                "lesson_id": metrics.lesson_id,
                "difficulty": "challenge"
            }
        )

    async def _suggest_break(self, user_id: str, trigger: AdaptationTrigger,
                           metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest taking a break"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"break_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="pacing",
            priority=1,
            title="Take a Break",
            description="You've been working hard! Taking a short break can help you learn better",
            action_data={
                "action": "suggest_break",
                "break_duration_minutes": 10,
                "resume_lesson_id": metrics.lesson_id
            },
            expires_at=datetime.now() + timedelta(hours=1)
        )

    async def _suggest_different_approach(self, user_id: str, trigger: AdaptationTrigger,
                                        metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest trying a different learning approach"""
        profile = self.learner_profiles.get(user_id)
        if not profile:
            return None

        # Suggest alternative approach based on learning style
        approach_suggestions = {
            LearningStyle.VISUAL: "visual explanations and diagrams",
            LearningStyle.AUDITORY: "audio explanations and discussions",
            LearningStyle.KINESTHETIC: "interactive exercises and hands-on activities",
            LearningStyle.READING_WRITING: "text-based explanations and note-taking"
        }

        suggested_approach = approach_suggestions.get(profile.learning_style, "interactive content")

        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"approach_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="style",
            priority=1,
            title="Try a Different Approach",
            description=f"Let's try {suggested_approach} to help you understand better",
            action_data={
                "action": "change_learning_approach",
                "target_style": profile.learning_style,
                "lesson_id": metrics.lesson_id
            }
        )

    async def _suggest_simpler_explanation(self, user_id: str, trigger: AdaptationTrigger,
                                         metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest simpler explanation"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"simple_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=1,
            title="Simpler Explanation",
            description="Let me explain this concept in a simpler way",
            action_data={
                "action": "show_simple_explanation",
                "lesson_id": metrics.lesson_id,
                "explanation_level": "basic"
            }
        )

    async def _suggest_concept_review(self, user_id: str, trigger: AdaptationTrigger,
                                    metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest reviewing core concepts"""
        mistake_categories = [mistake.get('category') for mistake in metrics.mistakes]
        most_common_mistake = max(set(mistake_categories), key=mistake_categories.count) if mistake_categories else "general"

        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"concept_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=1,
            title="Review Core Concepts",
            description=f"Let's review the fundamentals of {most_common_mistake}",
            action_data={
                "action": "show_concept_review",
                "concept": most_common_mistake,
                "lesson_id": metrics.lesson_id
            }
        )

    async def _suggest_alternative_learning_path(self, user_id: str, trigger: AdaptationTrigger,
                                               metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest alternative learning path"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"altpath_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=1,
            title="Alternative Learning Path",
            description="Let's try a different way to learn this topic",
            action_data={
                "action": "show_alternative_path",
                "current_lesson": metrics.lesson_id,
                "alternative_approach": "step_by_step"
            }
        )

    async def _suggest_one_on_one_help(self, user_id: str, trigger: AdaptationTrigger,
                                     metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest one-on-one help"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"help_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="support",
            priority=1,
            title="Get Personal Help",
            description="Would you like personalized help with this topic?",
            action_data={
                "action": "request_tutor_help",
                "lesson_id": metrics.lesson_id,
                "help_type": "concept_clarification"
            }
        )

    async def _suggest_interactive_content(self, user_id: str, trigger: AdaptationTrigger,
                                         metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest more interactive content"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"interactive_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="content",
            priority=1,
            title="Interactive Learning",
            description="Try these interactive exercises to make learning more engaging!",
            action_data={
                "action": "show_interactive_content",
                "lesson_id": metrics.lesson_id,
                "content_type": "interactive_exercises"
            }
        )

    async def _suggest_gamification(self, user_id: str, trigger: AdaptationTrigger,
                                  metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest gamified learning elements"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"game_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="engagement",
            priority=2,
            title="Learning Game",
            description="Turn your learning into a game! Earn points and unlock achievements",
            action_data={
                "action": "enable_gamification",
                "lesson_id": metrics.lesson_id,
                "game_elements": ["points", "badges", "leaderboard"]
            }
        )

    async def _suggest_break_or_change_topic(self, user_id: str, trigger: AdaptationTrigger,
                                           metrics: PerformanceMetrics) -> Optional[AdaptiveRecommendation]:
        """Suggest break or topic change"""
        return AdaptiveRecommendation(
            user_id=user_id,
            recommendation_id=f"change_{metrics.lesson_id}_{int(time.time())}",
            trigger=trigger,
            recommendation_type="engagement",
            priority=1,
            title="Try Something Different",
            description="Sometimes a change of topic can help. Want to try something else for a bit?",
            action_data={
                "action": "suggest_topic_change",
                "current_lesson": metrics.lesson_id,
                "alternative_topics": ["review_favorites", "quick_quiz", "fun_facts"]
            }
        )

    async def _store_and_send_recommendations(self, user_id: str,
                                           recommendations: List[AdaptiveRecommendation]):
        """Store recommendations and send to user via real-time sync"""
        if not recommendations:
            return

        # Store recommendations
        if user_id not in self.active_recommendations:
            self.active_recommendations[user_id] = []

        self.active_recommendations[user_id].extend(recommendations)

        # Send high-priority recommendations immediately
        high_priority_recs = [r for r in recommendations if r.priority == 1]
        for rec in high_priority_recs:
            await realtime_sync.send_adaptive_suggestion(
                user_id=user_id,
                course_id="adaptive_system",  # System-generated
                suggestion_data={
                    "recommendation_id": rec.recommendation_id,
                    "title": rec.title,
                    "description": rec.description,
                    "action_data": rec.action_data,
                    "priority": rec.priority,
                    "trigger": rec.trigger
                }
            )

        logger.info(f"Generated {len(recommendations)} adaptive recommendations for user {user_id}")

    async def get_recommendations(self, user_id: str, limit: int = 5) -> List[AdaptiveRecommendation]:
        """Get active recommendations for a user"""
        user_recs = self.active_recommendations.get(user_id, [])

        # Filter out expired recommendations
        now = datetime.now()
        active_recs = [
            rec for rec in user_recs
            if not rec.expires_at or rec.expires_at > now
        ]

        # Sort by priority and return limited results
        active_recs.sort(key=lambda x: x.priority)
        return active_recs[:limit]

    async def implement_recommendation(self, user_id: str, recommendation_id: str) -> bool:
        """Mark recommendation as implemented"""
        user_recs = self.active_recommendations.get(user_id, [])

        for rec in user_recs:
            if rec.recommendation_id == recommendation_id:
                rec.implemented = True
                logger.info(f"Implemented recommendation {recommendation_id} for user {user_id}")
                return True

        return False

    async def _handle_progress_update(self, event: SyncEvent):
        """Handle real-time progress update events"""
        try:
            await self.track_performance(
                user_id=event.user_id,
                course_id=event.course_id,
                lesson_id=event.lesson_id or "unknown",
                performance_data=event.payload
            )
        except Exception as e:
            logger.error(f"Error handling progress update: {e}")

    async def _handle_lesson_completion(self, event: SyncEvent):
        """Handle lesson completion events"""
        try:
            # Track completion performance
            completion_data = event.payload
            completion_data['completion_rate'] = 1.0  # Fully completed

            await self.track_performance(
                user_id=event.user_id,
                course_id=event.course_id,
                lesson_id=event.lesson_id or "unknown",
                performance_data=completion_data
            )
        except Exception as e:
            logger.error(f"Error handling lesson completion: {e}")

    async def _handle_quiz_submission(self, event: SyncEvent):
        """Handle quiz submission events"""
        try:
            quiz_data = event.payload
            performance_data = {
                'accuracy_rate': quiz_data.get('score', 0) / quiz_data.get('max_score', 1),
                'completion_rate': 1.0,
                'time_spent_minutes': quiz_data.get('time_spent_seconds', 0) / 60,
                'attempts_count': quiz_data.get('attempt_number', 1),
                'mistakes': quiz_data.get('incorrect_answers', [])
            }

            await self.track_performance(
                user_id=event.user_id,
                course_id=event.course_id,
                lesson_id=event.lesson_id or "quiz",
                performance_data=performance_data
            )
        except Exception as e:
            logger.error(f"Error handling quiz submission: {e}")

    def get_learning_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive learning analytics for a user"""
        profile = self.learner_profiles.get(user_id)
        history = self.performance_history.get(user_id, [])
        recommendations = self.active_recommendations.get(user_id, [])

        if not profile or not history:
            return {}

        # Calculate analytics
        recent_sessions = history[-10:]
        avg_accuracy = statistics.mean([s.accuracy_rate for s in recent_sessions]) if recent_sessions else 0
        avg_completion = statistics.mean([s.completion_rate for s in recent_sessions]) if recent_sessions else 0
        total_time = sum([s.time_spent_minutes for s in history])

        return {
            "user_id": user_id,
            "profile": profile.dict(),
            "performance_summary": {
                "total_sessions": len(history),
                "recent_avg_accuracy": round(avg_accuracy, 3),
                "recent_avg_completion": round(avg_completion, 3),
                "total_learning_time": round(total_time, 2),
                "strengths": profile.strengths,
                "weaknesses": profile.weaknesses
            },
            "active_recommendations": len([r for r in recommendations if not r.implemented]),
            "learning_insights": self._generate_learning_insights_sync(user_id, profile, history)
        }

    async def _generate_learning_insights(self, user_id: str, profile: LearnerProfile,
                                        history: List[PerformanceMetrics]) -> List[str]:
        """Generate insights about learning patterns"""
        insights = []

        if len(history) < 3:
            insights.append("Keep learning to unlock personalized insights!")
            return insights

        # Performance trend analysis
        recent_accuracy = [m.accuracy_rate for m in history[-5:]]
        if len(recent_accuracy) >= 3:
            trend = recent_accuracy[-1] - recent_accuracy[0]
            if trend > 0.1:
                insights.append("Your performance is improving consistently!")
            elif trend < -0.1:
                insights.append("You might benefit from reviewing recent topics")

        # Learning pace insights
        avg_time = statistics.mean([m.time_spent_minutes for m in history[-5:]])
        if avg_time > profile.optimal_session_length * 1.5:
            insights.append("Consider breaking your study sessions into smaller chunks")
        elif avg_time < profile.optimal_session_length * 0.5:
            insights.append("You could potentially handle more challenging content")

        # Consistency insights
        completion_rates = [m.completion_rate for m in history[-7:]]
        if completion_rates and statistics.stdev(completion_rates) < 0.1:
            insights.append("You have excellent learning consistency!")

        # Strength utilization
        if profile.strengths:
            insights.append(f"Your strengths in {', '.join(profile.strengths[:2])} are helping you learn faster")

        return insights

    def _generate_learning_insights_sync(self, user_id: str, profile: LearnerProfile,
                                       history: List[PerformanceMetrics]) -> List[str]:
        """Generate insights about learning patterns (synchronous version)"""
        insights = []

        if len(history) < 3:
            insights.append("Keep learning to unlock personalized insights!")
            return insights

        # Performance trend analysis
        recent_accuracy = [m.accuracy_rate for m in history[-5:]]
        if len(recent_accuracy) >= 3:
            trend = recent_accuracy[-1] - recent_accuracy[0]
            if trend > 0.1:
                insights.append("Your performance is improving consistently!")
            elif trend < -0.1:
                insights.append("You might benefit from reviewing recent topics")

        # Learning pace insights
        avg_time = statistics.mean([m.time_spent_minutes for m in history[-5:]])
        if avg_time > profile.optimal_session_length * 1.5:
            insights.append("Consider breaking your study sessions into smaller chunks")
        elif avg_time < profile.optimal_session_length * 0.5:
            insights.append("You could potentially handle more challenging content")

        # Consistency insights
        completion_rates = [m.completion_rate for m in history[-7:]]
        if completion_rates and statistics.stdev(completion_rates) < 0.1:
            insights.append("You have excellent learning consistency!")

        # Strength utilization
        if profile.strengths:
            insights.append(f"Your strengths in {', '.join(profile.strengths[:2])} are helping you learn faster")

        return insights

# Global adaptive learning engine instance
adaptive_engine = AdaptiveLearningEngine()