#!/usr/bin/env python3
"""
Gamification Engine for Lyo Platform
Comprehensive gamification system with achievements, progress tracking,
leaderboards, rewards, and motivational mechanics for enhanced learning engagement
"""

from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict


class AchievementCategory(Enum):
    """Categories of achievements"""
    LEARNING = "learning"
    SOCIAL = "social"
    CONSISTENCY = "consistency"
    MASTERY = "mastery"
    EXPLORATION = "exploration"
    CONTRIBUTION = "contribution"
    COLLABORATION = "collaboration"


class BadgeRarity(Enum):
    """Badge rarity levels"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class ProgressType(Enum):
    """Types of progress tracking"""
    CUMULATIVE = "cumulative"  # Total count (e.g., total courses completed)
    STREAK = "streak"  # Consecutive count (e.g., daily login streak)
    MILESTONE = "milestone"  # Specific targets (e.g., complete 5 courses)
    PERCENTAGE = "percentage"  # Progress towards 100% (e.g., course completion)


@dataclass
class Achievement:
    """Individual achievement definition"""
    achievement_id: str
    name: str
    description: str
    category: AchievementCategory
    badge_rarity: BadgeRarity
    points: int
    requirements: Dict[str, Any]  # Conditions to unlock
    icon: str = ""
    hidden: bool = False  # Hidden until achieved
    repeatable: bool = False
    prerequisites: List[str] = field(default_factory=list)
    reward_items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserAchievement:
    """User's earned achievement"""
    user_id: str
    achievement_id: str
    earned_at: datetime
    progress_snapshot: Dict[str, Any] = field(default_factory=dict)
    celebration_shown: bool = False


@dataclass
class ProgressTracker:
    """Tracks user progress towards achievements"""
    user_id: str
    metric_name: str
    progress_type: ProgressType
    current_value: float
    target_value: float
    last_updated: datetime = field(default_factory=datetime.utcnow)
    streak_count: int = 0
    best_streak: int = 0
    milestone_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Leaderboard:
    """Leaderboard for competitive elements"""
    leaderboard_id: str
    name: str
    description: str
    metric: str  # What is being measured
    timeframe: str  # daily, weekly, monthly, all_time
    max_participants: int = 100
    participants: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    rewards: Dict[str, Any] = field(default_factory=dict)  # Rewards for top positions


@dataclass
class UserProfile:
    """User's gamification profile"""
    user_id: str
    display_name: str
    total_points: int = 0
    level: int = 1
    experience_points: int = 0
    achievements_earned: List[str] = field(default_factory=list)
    badges: List[str] = field(default_factory=list)
    streaks: Dict[str, int] = field(default_factory=dict)
    preferred_challenges: List[str] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Challenge:
    """Timed challenge for users"""
    challenge_id: str
    name: str
    description: str
    category: str
    difficulty: str  # easy, medium, hard, expert
    duration_days: int
    requirements: Dict[str, Any]
    rewards: Dict[str, Any]
    start_date: datetime
    end_date: datetime
    participants: List[str] = field(default_factory=list)
    leaderboard_id: Optional[str] = None
    is_active: bool = True


class GamificationEngine:
    """Core gamification engine for the Lyo platform"""

    def __init__(self):
        self.achievements: Dict[str, Achievement] = {}
        self.user_profiles: Dict[str, UserProfile] = {}
        self.user_achievements: Dict[str, List[UserAchievement]] = defaultdict(list)
        self.progress_trackers: Dict[str, Dict[str, ProgressTracker]] = defaultdict(dict)
        self.leaderboards: Dict[str, Leaderboard] = {}
        self.challenges: Dict[str, Challenge] = {}
        self.point_multipliers: Dict[str, float] = {"default": 1.0}
        self.level_thresholds = self._calculate_level_thresholds()

        # Initialize default achievements
        self._initialize_default_achievements()
        self._initialize_default_leaderboards()

    def _calculate_level_thresholds(self) -> List[int]:
        """Calculate experience points needed for each level"""
        thresholds = [0]  # Level 1 starts at 0
        for level in range(2, 101):  # Support up to level 100
            # Exponential growth: each level requires more XP
            xp_needed = int(100 * (level ** 1.5))
            thresholds.append(thresholds[-1] + xp_needed)
        return thresholds

    def _initialize_default_achievements(self):
        """Initialize default achievement set"""
        default_achievements = [
            # Learning achievements
            Achievement(
                achievement_id="first_lesson",
                name="First Steps",
                description="Complete your first lesson",
                category=AchievementCategory.LEARNING,
                badge_rarity=BadgeRarity.COMMON,
                points=10,
                requirements={"lessons_completed": 1}
            ),
            Achievement(
                achievement_id="course_graduate",
                name="Course Graduate",
                description="Complete your first course",
                category=AchievementCategory.LEARNING,
                badge_rarity=BadgeRarity.UNCOMMON,
                points=50,
                requirements={"courses_completed": 1}
            ),
            Achievement(
                achievement_id="knowledge_seeker",
                name="Knowledge Seeker",
                description="Complete 10 courses",
                category=AchievementCategory.LEARNING,
                badge_rarity=BadgeRarity.RARE,
                points=200,
                requirements={"courses_completed": 10}
            ),

            # Social achievements
            Achievement(
                achievement_id="helpful_peer",
                name="Helpful Peer",
                description="Help 5 fellow learners",
                category=AchievementCategory.SOCIAL,
                badge_rarity=BadgeRarity.UNCOMMON,
                points=30,
                requirements={"peers_helped": 5}
            ),
            Achievement(
                achievement_id="knowledge_sharer",
                name="Knowledge Sharer",
                description="Make 10 knowledge contributions",
                category=AchievementCategory.CONTRIBUTION,
                badge_rarity=BadgeRarity.RARE,
                points=100,
                requirements={"knowledge_contributions": 10}
            ),

            # Consistency achievements
            Achievement(
                achievement_id="daily_learner",
                name="Daily Learner",
                description="Learn for 7 consecutive days",
                category=AchievementCategory.CONSISTENCY,
                badge_rarity=BadgeRarity.UNCOMMON,
                points=40,
                requirements={"daily_streak": 7}
            ),
            Achievement(
                achievement_id="dedication_master",
                name="Dedication Master",
                description="Learn for 30 consecutive days",
                category=AchievementCategory.CONSISTENCY,
                badge_rarity=BadgeRarity.EPIC,
                points=150,
                requirements={"daily_streak": 30}
            ),

            # Mastery achievements
            Achievement(
                achievement_id="perfect_score",
                name="Perfect Score",
                description="Achieve 100% on any assessment",
                category=AchievementCategory.MASTERY,
                badge_rarity=BadgeRarity.RARE,
                points=75,
                requirements={"perfect_assessments": 1}
            ),
            Achievement(
                achievement_id="subject_expert",
                name="Subject Expert",
                description="Master a subject area (90%+ average)",
                category=AchievementCategory.MASTERY,
                badge_rarity=BadgeRarity.EPIC,
                points=200,
                requirements={"subject_mastery": 0.9}
            ),

            # Exploration achievements
            Achievement(
                achievement_id="curious_mind",
                name="Curious Mind",
                description="Explore 5 different subject areas",
                category=AchievementCategory.EXPLORATION,
                badge_rarity=BadgeRarity.RARE,
                points=80,
                requirements={"subjects_explored": 5}
            )
        ]

        for achievement in default_achievements:
            self.achievements[achievement.achievement_id] = achievement

    def _initialize_default_leaderboards(self):
        """Initialize default leaderboards"""
        default_leaderboards = [
            Leaderboard(
                leaderboard_id="weekly_points",
                name="Weekly Champions",
                description="Top point earners this week",
                metric="weekly_points",
                timeframe="weekly"
            ),
            Leaderboard(
                leaderboard_id="monthly_courses",
                name="Monthly Graduates",
                description="Most courses completed this month",
                metric="courses_completed",
                timeframe="monthly"
            ),
            Leaderboard(
                leaderboard_id="all_time_contributions",
                name="Knowledge Heroes",
                description="All-time knowledge contributors",
                metric="knowledge_contributions",
                timeframe="all_time"
            )
        ]

        for leaderboard in default_leaderboards:
            self.leaderboards[leaderboard.leaderboard_id] = leaderboard

    async def create_user_profile(self, user_id: str, display_name: str) -> UserProfile:
        """Create a new user gamification profile"""
        profile = UserProfile(
            user_id=user_id,
            display_name=display_name
        )

        self.user_profiles[user_id] = profile
        return profile

    async def track_user_action(self, user_id: str, action: str,
                              metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Track user action and update progress/achievements"""
        if user_id not in self.user_profiles:
            await self.create_user_profile(user_id, f"User_{user_id}")

        metadata = metadata or {}
        points_earned = 0
        achievements_unlocked = []
        level_up = False

        # Update progress trackers based on action
        progress_updates = await self._update_progress_trackers(user_id, action, metadata)

        # Check for achievement unlocks
        new_achievements = await self._check_achievement_unlocks(user_id)
        achievements_unlocked.extend(new_achievements)

        # Calculate points earned
        base_points = self._calculate_action_points(action, metadata)
        multiplier = self._get_point_multiplier(user_id, action)
        points_earned = int(base_points * multiplier)

        # Award points and check for level up
        if points_earned > 0:
            level_up = await self._award_points(user_id, points_earned)

        # Update leaderboards
        await self._update_leaderboards(user_id, action, metadata)

        # Update user activity
        self.user_profiles[user_id].last_activity = datetime.utcnow()

        return {
            "points_earned": points_earned,
            "achievements_unlocked": achievements_unlocked,
            "level_up": level_up,
            "progress_updates": progress_updates,
            "current_level": self.user_profiles[user_id].level,
            "total_points": self.user_profiles[user_id].total_points
        }

    async def _update_progress_trackers(self, user_id: str, action: str,
                                      metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update progress trackers based on user action"""
        updates = []

        # Define action mappings to progress metrics
        action_mappings = {
            "lesson_completed": [("lessons_completed", 1), ("daily_activity", 1)],
            "course_completed": [("courses_completed", 1), ("subjects_explored", metadata.get("subject", ""))],
            "assessment_passed": [("assessments_passed", 1)],
            "perfect_score": [("perfect_assessments", 1)],
            "peer_helped": [("peers_helped", 1)],
            "knowledge_shared": [("knowledge_contributions", 1)],
            "daily_login": [("daily_streak", 1), ("login_count", 1)]
        }

        if action in action_mappings:
            for metric_name, value in action_mappings[action]:
                update = await self._update_progress_metric(user_id, metric_name, value, metadata)
                if update:
                    updates.append(update)

        return updates

    async def _update_progress_metric(self, user_id: str, metric_name: str,
                                    value: Any, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a specific progress metric for a user"""
        if user_id not in self.progress_trackers:
            self.progress_trackers[user_id] = {}

        if metric_name not in self.progress_trackers[user_id]:
            # Create new progress tracker
            progress_type = self._get_progress_type(metric_name)
            target_value = self._get_target_value(metric_name)

            self.progress_trackers[user_id][metric_name] = ProgressTracker(
                user_id=user_id,
                metric_name=metric_name,
                progress_type=progress_type,
                current_value=0,
                target_value=target_value
            )

        tracker = self.progress_trackers[user_id][metric_name]

        if tracker.progress_type == ProgressType.CUMULATIVE:
            if isinstance(value, str):  # For subject exploration
                if value and value not in [item["value"] for item in tracker.milestone_history]:
                    tracker.current_value += 1
                    tracker.milestone_history.append({
                        "value": value,
                        "timestamp": datetime.utcnow().isoformat()
                    })
            else:
                tracker.current_value += value

        elif tracker.progress_type == ProgressType.STREAK:
            if metric_name == "daily_streak":
                today = datetime.utcnow().date()
                last_update_date = tracker.last_updated.date()

                if last_update_date == today:
                    # Already updated today
                    return None
                elif last_update_date == today - timedelta(days=1):
                    # Continue streak
                    tracker.streak_count += 1
                    tracker.current_value = tracker.streak_count
                else:
                    # Streak broken, reset
                    tracker.streak_count = 1
                    tracker.current_value = 1

                tracker.best_streak = max(tracker.best_streak, tracker.streak_count)

        tracker.last_updated = datetime.utcnow()

        # Calculate previous value safely
        if tracker.progress_type == ProgressType.CUMULATIVE:
            if isinstance(value, str):
                previous_value = tracker.current_value - 1 if tracker.current_value > 0 else 0
            else:
                previous_value = tracker.current_value - value
        else:
            previous_value = tracker.current_value

        return {
            "metric_name": metric_name,
            "previous_value": previous_value,
            "current_value": tracker.current_value,
            "progress_percentage": min(100, (tracker.current_value / tracker.target_value) * 100) if tracker.target_value > 0 else 0
        }

    def _get_progress_type(self, metric_name: str) -> ProgressType:
        """Get progress type for a metric"""
        streak_metrics = ["daily_streak", "weekly_streak"]
        if metric_name in streak_metrics:
            return ProgressType.STREAK
        return ProgressType.CUMULATIVE

    def _get_target_value(self, metric_name: str) -> float:
        """Get target value for a metric (for progress calculation)"""
        target_values = {
            "lessons_completed": 100,
            "courses_completed": 50,
            "subjects_explored": 10,
            "assessments_passed": 50,
            "perfect_assessments": 10,
            "peers_helped": 25,
            "knowledge_contributions": 20,
            "daily_streak": 30,
            "login_count": 365
        }
        return target_values.get(metric_name, 1)

    async def _check_achievement_unlocks(self, user_id: str) -> List[str]:
        """Check if user has unlocked any new achievements"""
        if user_id not in self.progress_trackers:
            return []

        user_progress = self.progress_trackers[user_id]
        user_achievements = {ach.achievement_id for ach in self.user_achievements[user_id]}
        new_achievements = []

        for achievement_id, achievement in self.achievements.items():
            if achievement_id in user_achievements:
                continue  # Already earned

            # Check if requirements are met
            requirements_met = True
            for req_name, req_value in achievement.requirements.items():
                if req_name in user_progress:
                    tracker = user_progress[req_name]
                    if tracker.current_value < req_value:
                        requirements_met = False
                        break
                else:
                    requirements_met = False
                    break

            if requirements_met:
                # Check prerequisites
                if achievement.prerequisites:
                    prereqs_met = all(prereq in user_achievements for prereq in achievement.prerequisites)
                    if not prereqs_met:
                        requirements_met = False

                if requirements_met:
                    # Award achievement
                    user_achievement = UserAchievement(
                        user_id=user_id,
                        achievement_id=achievement_id,
                        earned_at=datetime.utcnow(),
                        progress_snapshot={
                            metric: tracker.current_value
                            for metric, tracker in user_progress.items()
                        }
                    )

                    self.user_achievements[user_id].append(user_achievement)
                    new_achievements.append(achievement_id)

                    # Award achievement points
                    await self._award_points(user_id, achievement.points)

        return new_achievements

    def _calculate_action_points(self, action: str, metadata: Dict[str, Any]) -> int:
        """Calculate base points for an action"""
        point_values = {
            "lesson_completed": 10,
            "course_completed": 50,
            "assessment_passed": 15,
            "perfect_score": 25,
            "peer_helped": 5,
            "knowledge_shared": 20,
            "daily_login": 2,
            "study_group_joined": 10,
            "collaboration_session": 15
        }

        base_points = point_values.get(action, 1)

        # Apply difficulty multipliers
        difficulty = metadata.get("difficulty", "medium")
        difficulty_multipliers = {"easy": 0.8, "medium": 1.0, "hard": 1.3, "expert": 1.6}
        multiplier = difficulty_multipliers.get(difficulty, 1.0)

        return int(base_points * multiplier)

    def _get_point_multiplier(self, user_id: str, action: str) -> float:
        """Get point multiplier for user (based on streaks, events, etc.)"""
        multiplier = self.point_multipliers.get("default", 1.0)

        # Streak bonus
        if user_id in self.progress_trackers and "daily_streak" in self.progress_trackers[user_id]:
            streak = self.progress_trackers[user_id]["daily_streak"].streak_count
            if streak >= 7:
                multiplier += 0.1  # 10% bonus for 7+ day streak
            if streak >= 30:
                multiplier += 0.2  # Additional 20% bonus for 30+ day streak

        # Weekend bonus
        if datetime.utcnow().weekday() >= 5:  # Saturday or Sunday
            multiplier += 0.05

        return multiplier

    async def _award_points(self, user_id: str, points: int) -> bool:
        """Award points to user and check for level up"""
        if user_id not in self.user_profiles:
            return False

        profile = self.user_profiles[user_id]
        old_level = profile.level

        profile.total_points += points
        profile.experience_points += points

        # Check for level up
        new_level = self._calculate_level(profile.experience_points)
        level_up = new_level > old_level

        if level_up:
            profile.level = new_level
            # Award level up bonus points
            bonus_points = new_level * 10
            profile.total_points += bonus_points

        return level_up

    def _calculate_level(self, experience_points: int) -> int:
        """Calculate user level based on experience points"""
        for level, threshold in enumerate(self.level_thresholds, 1):
            if experience_points < threshold:
                return level - 1
        return len(self.level_thresholds)  # Max level

    async def _update_leaderboards(self, user_id: str, action: str, metadata: Dict[str, Any]):
        """Update relevant leaderboards"""
        # Update weekly points leaderboard
        if "weekly_points" in self.leaderboards:
            await self._update_leaderboard_entry("weekly_points", user_id, action, metadata)

        # Update course completion leaderboard
        if action == "course_completed" and "monthly_courses" in self.leaderboards:
            await self._update_leaderboard_entry("monthly_courses", user_id, action, metadata)

        # Update knowledge contributions leaderboard
        if action == "knowledge_shared" and "all_time_contributions" in self.leaderboards:
            await self._update_leaderboard_entry("all_time_contributions", user_id, action, metadata)

    async def _update_leaderboard_entry(self, leaderboard_id: str, user_id: str,
                                      action: str, metadata: Dict[str, Any]):
        """Update a user's entry in a specific leaderboard"""
        leaderboard = self.leaderboards[leaderboard_id]

        # Find existing entry
        user_entry = None
        for participant in leaderboard.participants:
            if participant["user_id"] == user_id:
                user_entry = participant
                break

        if not user_entry:
            # Create new entry
            user_entry = {
                "user_id": user_id,
                "display_name": self.user_profiles.get(user_id, {}).display_name if user_id in self.user_profiles else f"User_{user_id}",
                "score": 0,
                "rank": 0
            }
            leaderboard.participants.append(user_entry)

        # Update score based on leaderboard metric
        if leaderboard.metric == "weekly_points":
            points_earned = self._calculate_action_points(action, metadata)
            user_entry["score"] += points_earned
        elif leaderboard.metric == "courses_completed" and action == "course_completed":
            user_entry["score"] += 1
        elif leaderboard.metric == "knowledge_contributions" and action == "knowledge_shared":
            user_entry["score"] += 1

        # Sort and update ranks
        leaderboard.participants.sort(key=lambda x: x["score"], reverse=True)
        for i, participant in enumerate(leaderboard.participants):
            participant["rank"] = i + 1

        # Limit participants
        leaderboard.participants = leaderboard.participants[:leaderboard.max_participants]
        leaderboard.last_updated = datetime.utcnow()

    async def create_challenge(self, challenge_data: Dict[str, Any]) -> Challenge:
        """Create a new timed challenge"""
        challenge_id = f"challenge_{int(datetime.utcnow().timestamp())}"

        challenge = Challenge(
            challenge_id=challenge_id,
            name=challenge_data["name"],
            description=challenge_data["description"],
            category=challenge_data.get("category", "general"),
            difficulty=challenge_data.get("difficulty", "medium"),
            duration_days=challenge_data.get("duration_days", 7),
            requirements=challenge_data["requirements"],
            rewards=challenge_data.get("rewards", {}),
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=challenge_data.get("duration_days", 7))
        )

        self.challenges[challenge_id] = challenge
        return challenge

    async def join_challenge(self, user_id: str, challenge_id: str) -> bool:
        """Join a challenge"""
        if challenge_id not in self.challenges:
            return False

        challenge = self.challenges[challenge_id]

        if not challenge.is_active or datetime.utcnow() > challenge.end_date:
            return False

        if user_id not in challenge.participants:
            challenge.participants.append(user_id)

        return True

    async def get_user_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive gamification dashboard for user"""
        if user_id not in self.user_profiles:
            return {"error": "User profile not found"}

        profile = self.user_profiles[user_id]
        user_progress = self.progress_trackers.get(user_id, {})
        user_achievements_list = self.user_achievements.get(user_id, [])

        # Calculate progress to next level
        current_level = profile.level
        current_xp = profile.experience_points
        next_level_xp = self.level_thresholds[current_level] if current_level < len(self.level_thresholds) - 1 else current_xp
        level_progress = ((current_xp - self.level_thresholds[current_level - 1]) /
                         (next_level_xp - self.level_thresholds[current_level - 1]) * 100) if current_level < len(self.level_thresholds) - 1 else 100

        # Recent achievements (last 5)
        recent_achievements = sorted(user_achievements_list, key=lambda x: x.earned_at, reverse=True)[:5]

        # Active challenges
        active_challenges = [
            challenge for challenge in self.challenges.values()
            if user_id in challenge.participants and challenge.is_active and datetime.utcnow() <= challenge.end_date
        ]

        # Leaderboard positions
        leaderboard_positions = {}
        for lb_id, leaderboard in self.leaderboards.items():
            for participant in leaderboard.participants:
                if participant["user_id"] == user_id:
                    leaderboard_positions[lb_id] = {
                        "rank": participant["rank"],
                        "score": participant["score"],
                        "total_participants": len(leaderboard.participants)
                    }
                    break

        return {
            "profile": {
                "user_id": profile.user_id,
                "display_name": profile.display_name,
                "level": profile.level,
                "experience_points": profile.experience_points,
                "total_points": profile.total_points,
                "level_progress_percentage": level_progress,
                "achievements_count": len(user_achievements_list)
            },
            "progress": {
                metric_name: {
                    "current_value": tracker.current_value,
                    "target_value": tracker.target_value,
                    "progress_percentage": min(100, (tracker.current_value / tracker.target_value) * 100) if tracker.target_value > 0 else 0,
                    "streak_count": tracker.streak_count,
                    "best_streak": tracker.best_streak
                }
                for metric_name, tracker in user_progress.items()
            },
            "recent_achievements": [
                {
                    "achievement_id": ach.achievement_id,
                    "name": self.achievements[ach.achievement_id].name,
                    "description": self.achievements[ach.achievement_id].description,
                    "rarity": self.achievements[ach.achievement_id].badge_rarity.value,
                    "earned_at": ach.earned_at.isoformat()
                }
                for ach in recent_achievements
            ],
            "active_challenges": [
                {
                    "challenge_id": challenge.challenge_id,
                    "name": challenge.name,
                    "description": challenge.description,
                    "difficulty": challenge.difficulty,
                    "end_date": challenge.end_date.isoformat(),
                    "days_remaining": (challenge.end_date - datetime.utcnow()).days
                }
                for challenge in active_challenges
            ],
            "leaderboard_positions": leaderboard_positions
        }

    async def get_achievement_progress(self, user_id: str) -> Dict[str, Any]:
        """Get user's progress towards all achievements"""
        if user_id not in self.progress_trackers:
            return {}

        user_progress = self.progress_trackers[user_id]
        earned_achievements = {ach.achievement_id for ach in self.user_achievements.get(user_id, [])}

        progress_report = {
            "earned": [],
            "in_progress": [],
            "locked": []
        }

        for achievement_id, achievement in self.achievements.items():
            if achievement_id in earned_achievements:
                progress_report["earned"].append({
                    "achievement_id": achievement_id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "rarity": achievement.badge_rarity.value,
                    "points": achievement.points
                })
            else:
                # Check progress towards requirements
                requirements_progress = {}
                can_unlock = True

                for req_name, req_value in achievement.requirements.items():
                    if req_name in user_progress:
                        current = user_progress[req_name].current_value
                        requirements_progress[req_name] = {
                            "current": current,
                            "required": req_value,
                            "progress_percentage": min(100, (current / req_value) * 100)
                        }
                    else:
                        requirements_progress[req_name] = {
                            "current": 0,
                            "required": req_value,
                            "progress_percentage": 0
                        }
                        can_unlock = False

                achievement_data = {
                    "achievement_id": achievement_id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "rarity": achievement.badge_rarity.value,
                    "points": achievement.points,
                    "requirements_progress": requirements_progress,
                    "hidden": achievement.hidden
                }

                if can_unlock or any(progress["progress_percentage"] > 0 for progress in requirements_progress.values()):
                    progress_report["in_progress"].append(achievement_data)
                else:
                    progress_report["locked"].append(achievement_data)

        return progress_report


# Global gamification engine
gamification_engine = GamificationEngine()


# Convenience functions
async def track_learning_action(user_id: str, action: str, metadata: Dict[str, Any] = None):
    """Track a learning action and update gamification"""
    return await gamification_engine.track_user_action(user_id, action, metadata)


async def get_user_gamification_dashboard(user_id: str):
    """Get user's gamification dashboard"""
    return await gamification_engine.get_user_dashboard(user_id)


async def create_learning_challenge(challenge_data: Dict[str, Any]):
    """Create a new learning challenge"""
    return await gamification_engine.create_challenge(challenge_data)


if __name__ == "__main__":
    # Example usage and testing
    async def demo_gamification_engine():
        print("🎯 GAMIFICATION ENGINE DEMONSTRATION")
        print("=" * 70)

        engine = GamificationEngine()

        # Create user profiles
        print("👤 Creating user profiles...")
        users = ["alice_123", "bob_456", "carol_789"]

        for user_id in users:
            profile = await engine.create_user_profile(user_id, f"User_{user_id}")
            print(f"   ✅ Created profile: {profile.display_name}")

        # Simulate learning activities
        print("\\n📚 Simulating learning activities...")

        activities = [
            ("alice_123", "lesson_completed", {"difficulty": "medium", "subject": "python"}),
            ("alice_123", "lesson_completed", {"difficulty": "hard", "subject": "python"}),
            ("alice_123", "course_completed", {"subject": "python", "score": 95}),
            ("bob_456", "daily_login", {}),
            ("bob_456", "lesson_completed", {"difficulty": "easy", "subject": "javascript"}),
            ("carol_789", "knowledge_shared", {"type": "tutorial", "subject": "data_science"}),
            ("carol_789", "peer_helped", {"help_type": "code_review"}),
            ("alice_123", "perfect_score", {"assessment_id": "python_quiz_1"}),
        ]

        for user_id, action, metadata in activities:
            result = await engine.track_user_action(user_id, action, metadata)

            print(f"   📈 {user_id}: {action}")
            print(f"      Points earned: {result['points_earned']}")

            if result['achievements_unlocked']:
                for ach_id in result['achievements_unlocked']:
                    ach = engine.achievements[ach_id]
                    print(f"      🏆 Achievement unlocked: {ach.name}")

            if result['level_up']:
                print(f"      🆙 Level up! Now level {result['current_level']}")

        # Create and join challenge
        print("\\n🎯 Creating learning challenge...")
        challenge_data = {
            "name": "Python Mastery Week",
            "description": "Complete 5 Python lessons in 7 days",
            "category": "programming",
            "difficulty": "medium",
            "duration_days": 7,
            "requirements": {"lessons_completed": 5, "subject": "python"},
            "rewards": {"points": 100, "badge": "python_week_champion"}
        }

        challenge = await engine.create_challenge(challenge_data)
        print(f"   ✅ Challenge created: {challenge.name}")

        # Users join challenge
        for user_id in users:
            joined = await engine.join_challenge(user_id, challenge.challenge_id)
            print(f"   👥 {user_id} joined: {joined}")

        # Get user dashboard
        print("\\n📊 User Dashboard (Alice)...")
        dashboard = await engine.get_user_dashboard("alice_123")

        profile_info = dashboard["profile"]
        print(f"   👤 Level: {profile_info['level']} (XP: {profile_info['experience_points']})")
        print(f"   💰 Total Points: {profile_info['total_points']}")
        print(f"   🏆 Achievements: {profile_info['achievements_count']}")
        print(f"   📈 Level Progress: {profile_info['level_progress_percentage']:.1f}%")

        # Show recent achievements
        if dashboard["recent_achievements"]:
            print("   🎖️  Recent Achievements:")
            for ach in dashboard["recent_achievements"][:3]:
                print(f"      • {ach['name']} ({ach['rarity']})")

        # Achievement progress
        print("\\n🎯 Achievement Progress (Alice)...")
        achievement_progress = await engine.get_achievement_progress("alice_123")

        print(f"   ✅ Earned: {len(achievement_progress['earned'])}")
        print(f"   🔄 In Progress: {len(achievement_progress['in_progress'])}")
        print(f"   🔒 Locked: {len(achievement_progress['locked'])}")

        # Show in-progress achievements
        for ach in achievement_progress["in_progress"][:3]:
            print(f"   📋 {ach['name']}: ", end="")
            for req_name, req_progress in ach["requirements_progress"].items():
                print(f"{req_progress['current']}/{req_progress['required']} {req_name} ", end="")
            print()

        # Leaderboards
        print("\\n🏆 Leaderboards...")
        for lb_id, leaderboard in engine.leaderboards.items():
            print(f"   📊 {leaderboard.name}:")
            for participant in leaderboard.participants[:3]:
                print(f"      #{participant['rank']}: {participant['display_name']} ({participant['score']} points)")

        print(f"\\n🎉 GAMIFICATION ENGINE READY")
        print("   ✅ Achievement system with progress tracking")
        print("   ✅ Multi-level progression with XP")
        print("   ✅ Dynamic leaderboards")
        print("   ✅ Timed challenges and competitions")
        print("   ✅ Point multipliers and bonuses")
        print("   ✅ Comprehensive user dashboards")
        print("   ✅ Social recognition and badges")

    # Run demo if called directly
    asyncio.run(demo_gamification_engine())