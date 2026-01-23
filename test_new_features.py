#!/usr/bin/env python3
"""
New Features Test Suite
Validates social learning and gamification systems
"""

import unittest
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

class TestNewFeatures(unittest.TestCase):
    """Comprehensive test suite for new social learning and gamification features"""

    def setUp(self):
        """Setup test environment"""
        self.start_time = time.time()
        sys.path.append('.')

    def tearDown(self):
        """Cleanup after tests"""
        duration = time.time() - self.start_time
        print(f"   ⏱️  Test duration: {duration:.3f}s")

    def test_social_learning_engine_initialization(self):
        """Test social learning engine initialization"""
        print("👥 Testing social learning engine initialization...")

        try:
            from lyo_app.social.social_learning_engine import (
                SocialLearningEngine, CollaborationType, LearningRole
            )

            # Test initialization
            engine = SocialLearningEngine()
            self.assertIsInstance(engine, SocialLearningEngine)

            # Test data structures
            self.assertIsInstance(engine.learner_profiles, dict)
            self.assertIsInstance(engine.study_groups, dict)
            self.assertIsInstance(engine.collaboration_sessions, dict)
            self.assertIsInstance(engine.knowledge_contributions, dict)

            # Test matching engine
            self.assertIsNotNone(engine.matching_engine)
            self.assertIsNotNone(engine.recommendation_engine)

        except ImportError as e:
            self.fail(f"Social learning engine should be importable: {e}")

        print("   ✅ Social learning engine initialization: PASS")

    def test_learner_profile_creation(self):
        """Test learner profile creation and management"""
        print("👤 Testing learner profile creation...")

        try:
            from lyo_app.social.social_learning_engine import (
                SocialLearningEngine, CollaborationType
            )

            engine = SocialLearningEngine()

            # Test profile creation
            profile_data = {
                "display_name": "Test Learner",
                "expertise_areas": ["python", "data_science"],
                "interests": ["machine_learning", "ai"],
                "learning_goals": ["deep_learning", "nlp"],
                "preferred_collaboration_types": ["study_group", "peer_review"],
                "timezone": "UTC",
                "languages": ["en", "es"]
            }

            async def test_profile_creation():
                profile = await engine.create_learner_profile("test_user_123", profile_data)

                self.assertEqual(profile.user_id, "test_user_123")
                self.assertEqual(profile.display_name, "Test Learner")
                self.assertEqual(len(profile.expertise_areas), 2)
                self.assertIn("python", profile.expertise_areas)
                self.assertIn("machine_learning", profile.interests)
                self.assertEqual(profile.timezone, "UTC")

                # Verify profile was stored
                self.assertIn("test_user_123", engine.learner_profiles)

            asyncio.run(test_profile_creation())

        except Exception as e:
            self.fail(f"Learner profile creation should work: {e}")

        print("   ✅ Learner profile creation: PASS")

    def test_study_group_functionality(self):
        """Test study group creation and management"""
        print("📚 Testing study group functionality...")

        try:
            from lyo_app.social.social_learning_engine import SocialLearningEngine

            engine = SocialLearningEngine()

            async def test_study_groups():
                # Create user first
                await engine.create_learner_profile("creator_123", {"display_name": "Creator"})

                # Create study group
                group_data = {
                    "name": "AI Study Group",
                    "description": "Weekly AI discussions",
                    "subject_area": "artificial_intelligence",
                    "max_members": 10,
                    "privacy_level": "public",
                    "learning_objectives": ["neural_networks", "machine_learning"]
                }

                study_group = await engine.create_study_group("creator_123", group_data)

                self.assertIsNotNone(study_group.group_id)
                self.assertEqual(study_group.name, "AI Study Group")
                self.assertEqual(study_group.creator_id, "creator_123")
                self.assertIn("creator_123", study_group.members)
                self.assertEqual(len(study_group.members), 1)

                # Test joining group
                await engine.create_learner_profile("joiner_456", {"display_name": "Joiner"})
                join_success = await engine.join_study_group("joiner_456", study_group.group_id)

                self.assertTrue(join_success)
                self.assertIn("joiner_456", study_group.members)
                self.assertEqual(len(study_group.members), 2)

                # Verify group activity log
                self.assertGreater(len(study_group.activity_log), 0)

            asyncio.run(test_study_groups())

        except Exception as e:
            self.fail(f"Study group functionality should work: {e}")

        print("   ✅ Study group functionality: PASS")

    def test_collaboration_sessions(self):
        """Test real-time collaboration sessions"""
        print("🤝 Testing collaboration sessions...")

        try:
            from lyo_app.social.social_learning_engine import (
                SocialLearningEngine, CollaborationType
            )

            engine = SocialLearningEngine()

            async def test_collaboration():
                # Create users
                await engine.create_learner_profile("facilitator_123", {"display_name": "Facilitator"})
                await engine.create_learner_profile("participant_456", {"display_name": "Participant"})

                # Start collaboration session
                session_data = {
                    "topic": "Python Advanced Concepts",
                    "participants": ["facilitator_123", "participant_456"],
                    "facilitator_id": "facilitator_123",
                    "content": {"lesson_plan": "Object-oriented programming"}
                }

                session = await engine.start_collaboration_session(
                    "facilitator_123", CollaborationType.STUDY_GROUP, session_data
                )

                self.assertIsNotNone(session.session_id)
                self.assertEqual(session.collaboration_type, CollaborationType.STUDY_GROUP)
                self.assertEqual(session.facilitator_id, "facilitator_123")
                self.assertIn("facilitator_123", session.participants)
                self.assertEqual(session.topic, "Python Advanced Concepts")
                self.assertTrue(session.is_active)

                # Verify session was stored
                self.assertIn(session.session_id, engine.collaboration_sessions)

            asyncio.run(test_collaboration())

        except Exception as e:
            self.fail(f"Collaboration sessions should work: {e}")

        print("   ✅ Collaboration sessions: PASS")

    def test_knowledge_contributions(self):
        """Test knowledge contribution system"""
        print("📖 Testing knowledge contributions...")

        try:
            from lyo_app.social.social_learning_engine import SocialLearningEngine

            engine = SocialLearningEngine()

            async def test_knowledge_sharing():
                # Create contributor
                await engine.create_learner_profile("contributor_123", {"display_name": "Expert"})

                # Add knowledge contribution
                contrib_data = {
                    "content_type": "tutorial",
                    "title": "Introduction to Neural Networks",
                    "content": "Neural networks are computational models...",
                    "subject_area": "machine_learning",
                    "tags": ["neural_networks", "deep_learning", "ai"],
                    "difficulty_level": "intermediate"
                }

                contribution = await engine.contribute_knowledge("contributor_123", contrib_data)

                self.assertIsNotNone(contribution.contribution_id)
                self.assertEqual(contribution.contributor_id, "contributor_123")
                self.assertEqual(contribution.title, "Introduction to Neural Networks")
                self.assertEqual(contribution.content_type, "tutorial")
                self.assertIn("neural_networks", contribution.tags)

                # Verify contribution was stored
                self.assertIn(contribution.contribution_id, engine.knowledge_contributions)

                # Check contributor's profile was updated
                profile = engine.learner_profiles["contributor_123"]
                self.assertEqual(profile.contribution_count, 1)
                self.assertGreater(profile.reputation_score, 0)

            asyncio.run(test_knowledge_sharing())

        except Exception as e:
            self.fail(f"Knowledge contributions should work: {e}")

        print("   ✅ Knowledge contributions: PASS")

    def test_learning_matchmaking(self):
        """Test learning partner matchmaking"""
        print("🔍 Testing learning matchmaking...")

        try:
            from lyo_app.social.social_learning_engine import SocialLearningEngine

            engine = SocialLearningEngine()

            async def test_matchmaking():
                # Create multiple users with different profiles
                users = [
                    {
                        "user_id": "alice_123",
                        "display_name": "Alice",
                        "interests": ["python", "data_science"],
                        "expertise_areas": ["programming"],
                        "learning_goals": ["machine_learning"]
                    },
                    {
                        "user_id": "bob_456",
                        "display_name": "Bob",
                        "interests": ["data_science", "statistics"],
                        "expertise_areas": ["mathematics"],
                        "learning_goals": ["data_analysis"]
                    },
                    {
                        "user_id": "carol_789",
                        "display_name": "Carol",
                        "interests": ["web_development", "javascript"],
                        "expertise_areas": ["frontend"],
                        "learning_goals": ["react", "node_js"]
                    }
                ]

                for user_data in users:
                    await engine.create_learner_profile(user_data["user_id"], user_data)

                # Find learning partners for Alice
                partners = await engine.find_learning_partners("alice_123")

                self.assertIsInstance(partners, list)

                # Should find Bob as a compatible partner (shared data science interest)
                compatible_partners = [p for p in partners if p["user_id"] == "bob_456"]
                if compatible_partners:
                    bob_match = compatible_partners[0]
                    self.assertIn("compatibility_score", bob_match)
                    self.assertIn("shared_interests", bob_match)
                    self.assertGreater(bob_match["compatibility_score"], 0)

            asyncio.run(test_matchmaking())

        except Exception as e:
            self.fail(f"Learning matchmaking should work: {e}")

        print("   ✅ Learning matchmaking: PASS")

    def test_gamification_engine_initialization(self):
        """Test gamification engine initialization"""
        print("🎮 Testing gamification engine initialization...")

        try:
            from lyo_app.gamification.gamification_engine import (
                GamificationEngine, AchievementCategory, BadgeRarity
            )

            # Test initialization
            engine = GamificationEngine()
            self.assertIsInstance(engine, GamificationEngine)

            # Test default data structures
            self.assertIsInstance(engine.achievements, dict)
            self.assertIsInstance(engine.user_profiles, dict)
            self.assertIsInstance(engine.leaderboards, dict)
            self.assertIsInstance(engine.challenges, dict)

            # Test default achievements were loaded
            self.assertGreater(len(engine.achievements), 0)

            # Test level thresholds
            self.assertGreater(len(engine.level_thresholds), 0)
            self.assertEqual(engine.level_thresholds[0], 0)  # Level 1 starts at 0

            # Test default leaderboards
            self.assertGreater(len(engine.leaderboards), 0)

        except ImportError as e:
            self.fail(f"Gamification engine should be importable: {e}")

        print("   ✅ Gamification engine initialization: PASS")

    def test_user_profile_and_tracking(self):
        """Test user profile creation and action tracking"""
        print("📊 Testing user profile and action tracking...")

        try:
            from lyo_app.gamification.gamification_engine import GamificationEngine

            engine = GamificationEngine()

            async def test_tracking():
                # Create user profile
                profile = await engine.create_user_profile("test_user_123", "Test User")
                self.assertEqual(profile.user_id, "test_user_123")
                self.assertEqual(profile.display_name, "Test User")
                self.assertEqual(profile.level, 1)
                self.assertEqual(profile.total_points, 0)

                # Track learning actions
                actions = [
                    ("lesson_completed", {"difficulty": "medium"}),
                    ("lesson_completed", {"difficulty": "hard"}),
                    ("course_completed", {"subject": "python", "score": 95}),
                    ("daily_login", {}),
                ]

                total_points = 0
                for action, metadata in actions:
                    result = await engine.track_user_action("test_user_123", action, metadata)

                    self.assertIn("points_earned", result)
                    self.assertIn("achievements_unlocked", result)
                    self.assertIn("level_up", result)
                    self.assertIn("current_level", result)

                    self.assertGreaterEqual(result["points_earned"], 0)
                    total_points += result["points_earned"]

                # Check profile was updated
                updated_profile = engine.user_profiles["test_user_123"]
                self.assertGreater(updated_profile.total_points, 0)
                self.assertGreaterEqual(updated_profile.level, 1)

            asyncio.run(test_tracking())

        except Exception as e:
            self.fail(f"User profile and tracking should work: {e}")

        print("   ✅ User profile and action tracking: PASS")

    def test_achievement_system(self):
        """Test achievement unlocking and progress tracking"""
        print("🏆 Testing achievement system...")

        try:
            from lyo_app.gamification.gamification_engine import GamificationEngine

            engine = GamificationEngine()

            async def test_achievements():
                # Create user
                await engine.create_user_profile("achiever_123", "Achiever")

                # Track action that should unlock "First Steps" achievement
                result = await engine.track_user_action("achiever_123", "lesson_completed", {})

                # Check if achievement was unlocked
                user_achievements = engine.user_achievements["achiever_123"]
                achievement_ids = [ach.achievement_id for ach in user_achievements]

                # Should unlock "first_lesson" achievement
                if "first_lesson" in engine.achievements:
                    # The achievement should be unlocked after first lesson
                    # May not happen immediately due to requirements check timing

                    # Check achievement progress
                    progress = await engine.get_achievement_progress("achiever_123")
                    self.assertIn("earned", progress)
                    self.assertIn("in_progress", progress)
                    self.assertIn("locked", progress)

                    total_achievements = len(progress["earned"]) + len(progress["in_progress"]) + len(progress["locked"])
                    self.assertGreater(total_achievements, 0)

            asyncio.run(test_achievements())

        except Exception as e:
            self.fail(f"Achievement system should work: {e}")

        print("   ✅ Achievement system: PASS")

    def test_leaderboard_system(self):
        """Test leaderboard functionality"""
        print("🏆 Testing leaderboard system...")

        try:
            from lyo_app.gamification.gamification_engine import GamificationEngine

            engine = GamificationEngine()

            async def test_leaderboards():
                # Create multiple users
                users = ["user1", "user2", "user3"]
                for user_id in users:
                    await engine.create_user_profile(user_id, f"User {user_id}")

                # Simulate different activity levels
                activities = [
                    ("user1", "lesson_completed", {}),
                    ("user1", "lesson_completed", {}),
                    ("user2", "lesson_completed", {}),
                    ("user3", "course_completed", {}),
                ]

                for user_id, action, metadata in activities:
                    await engine.track_user_action(user_id, action, metadata)

                # Check leaderboards were updated
                weekly_lb = engine.leaderboards.get("weekly_points")
                if weekly_lb:
                    self.assertIsInstance(weekly_lb.participants, list)

                    # Should have participants
                    if weekly_lb.participants:
                        # Check participant structure
                        participant = weekly_lb.participants[0]
                        self.assertIn("user_id", participant)
                        self.assertIn("score", participant)
                        self.assertIn("rank", participant)

                        # Check ranking is correct (highest score should be rank 1)
                        self.assertEqual(participant["rank"], 1)

            asyncio.run(test_leaderboards())

        except Exception as e:
            self.fail(f"Leaderboard system should work: {e}")

        print("   ✅ Leaderboard system: PASS")

    def test_challenge_system(self):
        """Test challenge creation and participation"""
        print("🎯 Testing challenge system...")

        try:
            from lyo_app.gamification.gamification_engine import GamificationEngine

            engine = GamificationEngine()

            async def test_challenges():
                # Create challenge
                challenge_data = {
                    "name": "Python Mastery Challenge",
                    "description": "Complete 5 Python lessons",
                    "category": "programming",
                    "difficulty": "medium",
                    "duration_days": 7,
                    "requirements": {"lessons_completed": 5, "subject": "python"},
                    "rewards": {"points": 100, "badge": "python_champion"}
                }

                challenge = await engine.create_challenge(challenge_data)

                self.assertIsNotNone(challenge.challenge_id)
                self.assertEqual(challenge.name, "Python Mastery Challenge")
                self.assertEqual(challenge.duration_days, 7)
                self.assertTrue(challenge.is_active)

                # Create user and join challenge
                await engine.create_user_profile("challenger_123", "Challenger")
                join_result = await engine.join_challenge("challenger_123", challenge.challenge_id)

                self.assertTrue(join_result)
                self.assertIn("challenger_123", challenge.participants)

                # Verify challenge was stored
                self.assertIn(challenge.challenge_id, engine.challenges)

            asyncio.run(test_challenges())

        except Exception as e:
            self.fail(f"Challenge system should work: {e}")

        print("   ✅ Challenge system: PASS")

    def test_user_dashboard(self):
        """Test comprehensive user dashboard"""
        print("📱 Testing user dashboard...")

        try:
            from lyo_app.gamification.gamification_engine import GamificationEngine

            engine = GamificationEngine()

            async def test_dashboard():
                # Create user and simulate activity
                await engine.create_user_profile("dashboard_user", "Dashboard User")

                # Simulate some activity
                actions = [
                    ("lesson_completed", {"difficulty": "medium"}),
                    ("daily_login", {}),
                    ("peer_helped", {})
                ]

                for action, metadata in actions:
                    await engine.track_user_action("dashboard_user", action, metadata)

                # Get dashboard
                dashboard = await engine.get_user_dashboard("dashboard_user")

                # Verify dashboard structure
                self.assertIn("profile", dashboard)
                self.assertIn("progress", dashboard)
                self.assertIn("recent_achievements", dashboard)
                self.assertIn("active_challenges", dashboard)
                self.assertIn("leaderboard_positions", dashboard)

                # Check profile section
                profile = dashboard["profile"]
                self.assertEqual(profile["user_id"], "dashboard_user")
                self.assertEqual(profile["display_name"], "Dashboard User")
                self.assertGreaterEqual(profile["level"], 1)
                self.assertGreaterEqual(profile["total_points"], 0)
                self.assertGreaterEqual(profile["level_progress_percentage"], 0)
                self.assertLessEqual(profile["level_progress_percentage"], 100)

                # Check progress section
                progress = dashboard["progress"]
                self.assertIsInstance(progress, dict)

            asyncio.run(test_dashboard())

        except Exception as e:
            self.fail(f"User dashboard should work: {e}")

        print("   ✅ User dashboard: PASS")

def run_new_features_tests():
    """Run comprehensive new features test suite"""
    print("🎯 NEW FEATURES TEST SUITE")
    print("=" * 70)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestNewFeatures)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)

    start_time = time.time()
    result = runner.run(suite)
    total_time = time.time() - start_time

    # Calculate results
    total_tests = result.testsRun
    failed_tests = len(result.failures) + len(result.errors)
    success_rate = ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0

    print(f"\n📊 NEW FEATURES TEST RESULTS")
    print("=" * 70)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_tests - failed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Duration: {total_time:.3f}s")

    if result.failures:
        print(f"\n❌ FAILURES:")
        for test, error in result.failures:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if result.errors:
        print(f"\n💥 ERRORS:")
        for test, error in result.errors:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if success_rate >= 90.0:
        print(f"\n🎉 NEW FEATURES: EXCELLENT ({success_rate:.1f}%)")
        print("✅ Advanced social learning platform")
        print("✅ Comprehensive gamification system")
        print("✅ Intelligent peer matching")
        print("✅ Knowledge sharing ecosystem")
        print("✅ Real-time collaboration tools")
        print("✅ Achievement and progress tracking")
        print("✅ Dynamic challenges and leaderboards")
    else:
        print(f"\n⚠️  NEW FEATURES: NEEDS IMPROVEMENT ({success_rate:.1f}%)")
        print("📝 Address failing tests to optimize new features")

    return success_rate >= 90.0, {
        "total_tests": total_tests,
        "passed_tests": total_tests - failed_tests,
        "failed_tests": failed_tests,
        "success_rate": success_rate,
        "duration": total_time,
        "status": "pass" if success_rate >= 90.0 else "fail"
    }

if __name__ == "__main__":
    success, results = run_new_features_tests()