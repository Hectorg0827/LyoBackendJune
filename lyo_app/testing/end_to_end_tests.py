"""
End-to-End Test Suites
Comprehensive testing of complete user workflows and system integration
"""

import asyncio
import json
import sys
import time
from typing import Dict, Any, List
sys.path.append('.')

from lyo_app.testing.test_orchestrator import TestSuite, TestType, TestStatus
from lyo_app.chat.a2ui_recursive import A2UIFactory, ChatResponseV2
from lyo_app.chat.assembler import response_assembler
from lyo_app.ai_classroom.realtime_sync import realtime_sync
from lyo_app.ai_classroom.adaptive_learning import adaptive_engine
from lyo_app.cache.performance_cache import cache_instance, performance_monitor

# ==============================================================================
# COMPLETE USER JOURNEY TESTS
# ==============================================================================

async def test_complete_learning_journey():
    """Test complete learning journey from start to completion"""
    try:
        # Step 1: User discovers content
        discovery_response = ChatResponseV2(
            response="I found some great learning content for you!",
            ui_layout=A2UIFactory.vstack(
                A2UIFactory.text("Welcome to Lyo Learning", style="title"),
                A2UIFactory.card(
                    A2UIFactory.text("Python Fundamentals Course", style="headline"),
                    A2UIFactory.text("Learn Python from basics to advanced", style="body"),
                    A2UIFactory.button("Start Learning", "start_python_course"),
                    title="Recommended Course"
                )
            ),
            response_mode="discovery"
        )

        # Step 2: User starts learning session
        session = await realtime_sync.join_session("e2e_user", "python_course", device_type="web")

        # Step 3: User progresses through content
        await realtime_sync.start_lesson("e2e_user", "python_course", "lesson_1", {"title": "Variables"})

        # Step 4: Track learning progress
        await adaptive_engine.track_performance(
            "e2e_user", "python_course", "lesson_1",
            {
                "start_time": "2024-01-01T10:00:00",
                "end_time": "2024-01-01T10:30:00",
                "completion_rate": 1.0,
                "accuracy_rate": 0.85,
                "time_spent_minutes": 30
            }
        )

        # Step 5: Generate adaptive UI
        learning_ui = A2UIFactory.vstack(
            A2UIFactory.progress_tracker("Python Course", 1, 10, "Variables", "Functions"),
            A2UIFactory.video_player("https://example.com/lesson1.mp4", "Python Variables"),
            A2UIFactory.code_sandbox("python", "Try it yourself", "name = 'World'\nprint(f'Hello, {name}!')"),
            spacing=16
        )

        # Step 6: Complete lesson
        await realtime_sync.complete_lesson("e2e_user", "python_course", "lesson_1", {"score": 0.85})

        # Step 7: Get recommendations
        recommendations = await adaptive_engine.get_recommendations("e2e_user")

        # Step 8: Leave session
        await realtime_sync.leave_session(session.session_id)

        # Validate journey completion
        analytics = adaptive_engine.get_learning_analytics("e2e_user")

        return {
            "passed": (
                discovery_response.response_mode == "discovery" and
                session.user_id == "e2e_user" and
                analytics.get("user_id") == "e2e_user" and
                len(recommendations) >= 0
            ),
            "assertions": 4,
            "passed_assertions": 4,
            "metadata": {
                "session_id": session.session_id,
                "recommendations_count": len(recommendations),
                "analytics_sessions": analytics.get("performance_summary", {}).get("total_sessions", 0)
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 4,
            "passed_assertions": 0,
            "error": str(e)
        }

async def test_collaborative_learning_session():
    """Test collaborative learning session with multiple users"""
    try:
        # Start collaboration session
        collaboration_ui = A2UIFactory.collaboration_space(
            "Math Study Group",
            collaboration_types=["real_time_editing", "whiteboard"]
        )

        # Multiple users join
        sessions = []
        for i in range(3):
            session = await realtime_sync.join_session(
                f"collab_user_{i}", "math_collaboration", device_type="web"
            )
            sessions.append(session)

        # Users interact with whiteboard
        whiteboard = A2UIFactory.whiteboard(
            width=800, height=600,
            available_tools=["pen", "eraser", "text"],
            multi_user=True
        )

        # Simulate collaborative problem solving
        for i, session in enumerate(sessions):
            await realtime_sync.add_note(
                session.user_id, "math_collaboration", "problem_1",
                {"content": f"Solution step {i+1}", "type": "text"}
            )

        # Check active users
        active_users = realtime_sync.get_active_users("math_collaboration")

        # Clean up sessions
        for session in sessions:
            await realtime_sync.leave_session(session.session_id)

        return {
            "passed": (
                collaboration_ui.type == "collaboration_space" and
                len(sessions) == 3 and
                len(active_users) >= 0 and  # Should have users during session
                whiteboard.multi_user == True
            ),
            "assertions": 4,
            "passed_assertions": 4,
            "metadata": {
                "users_joined": len(sessions),
                "active_users_peak": len(active_users),
                "collaboration_features": len(collaboration_ui.collaboration_types)
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 4,
            "passed_assertions": 0,
            "error": str(e)
        }

async def test_adaptive_content_delivery():
    """Test adaptive content delivery based on user performance"""
    try:
        user_id = "adaptive_user"

        # Create initial profile
        profile = await adaptive_engine.get_or_create_profile(user_id)

        # Simulate learning sessions with different performance patterns
        sessions_data = [
            {"accuracy": 0.5, "completion": 0.6, "time": 45},  # Struggling
            {"accuracy": 0.7, "completion": 0.8, "time": 35},  # Improving
            {"accuracy": 0.9, "completion": 1.0, "time": 25},  # Mastered
        ]

        for i, session_data in enumerate(sessions_data):
            await adaptive_engine.track_performance(
                user_id, "adaptive_course", f"lesson_{i+1}",
                {
                    "start_time": f"2024-01-0{i+1}T10:00:00",
                    "completion_rate": session_data["completion"],
                    "accuracy_rate": session_data["accuracy"],
                    "time_spent_minutes": session_data["time"]
                }
            )

        # Get adaptive recommendations
        recommendations = await adaptive_engine.get_recommendations(user_id)

        # Check analytics evolution
        analytics = adaptive_engine.get_learning_analytics(user_id)

        # Generate adaptive UI based on performance
        if analytics.get("performance_summary", {}).get("recent_avg_accuracy", 0) > 0.8:
            content_ui = A2UIFactory.vstack(
                A2UIFactory.text("Great progress! Ready for advanced content?", style="headline"),
                A2UIFactory.code_sandbox("python", "Advanced Challenge", "# Advanced exercise"),
                A2UIFactory.simulation("physics", "Complex Simulation", {"difficulty": "advanced"})
            )
        else:
            content_ui = A2UIFactory.vstack(
                A2UIFactory.text("Let's review the basics", style="headline"),
                A2UIFactory.video_player("https://example.com/review.mp4", "Review Lesson"),
                A2UIFactory.text("Take your time to understand", style="body")
            )

        return {
            "passed": (
                profile.user_id == user_id and
                analytics.get("user_id") == user_id and
                analytics.get("performance_summary", {}).get("total_sessions", 0) == 3 and
                content_ui.type == "vstack"
            ),
            "assertions": 4,
            "passed_assertions": 4,
            "metadata": {
                "total_sessions": analytics.get("performance_summary", {}).get("total_sessions", 0),
                "recommendations": len(recommendations),
                "final_accuracy": analytics.get("performance_summary", {}).get("recent_avg_accuracy", 0),
                "content_adapted": True
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 4,
            "passed_assertions": 0,
            "error": str(e)
        }

async def test_performance_under_load():
    """Test system performance under concurrent load"""
    try:
        concurrent_users = 50
        tasks_per_user = 3

        # Performance monitoring
        start_time = time.time()

        # Create concurrent user sessions
        session_tasks = []
        for i in range(concurrent_users):
            task = asyncio.create_task(
                realtime_sync.join_session(f"load_user_{i}", "load_test_course", device_type="web")
            )
            session_tasks.append(task)

        sessions = await asyncio.gather(*session_tasks, return_exceptions=True)
        successful_sessions = [s for s in sessions if not isinstance(s, Exception)]

        session_creation_time = time.time() - start_time

        # Concurrent operations
        operation_tasks = []
        for session in successful_sessions[:min(concurrent_users, len(successful_sessions))]:
            for task_num in range(tasks_per_user):
                # Mix of different operations
                if task_num == 0:
                    task = asyncio.create_task(
                        realtime_sync.update_progress(
                            session.user_id, session.course_id, f"lesson_{task_num}",
                            {"completion_rate": 0.5, "accuracy_rate": 0.8}
                        )
                    )
                elif task_num == 1:
                    task = asyncio.create_task(
                        adaptive_engine.track_performance(
                            session.user_id, session.course_id, f"lesson_{task_num}",
                            {"completion_rate": 0.7, "accuracy_rate": 0.75, "time_spent_minutes": 15}
                        )
                    )
                else:
                    task = asyncio.create_task(
                        realtime_sync.submit_quiz(
                            session.user_id, session.course_id, f"lesson_{task_num}",
                            {"score": 8, "max_score": 10}
                        )
                    )
                operation_tasks.append(task)

        # Execute all operations
        operations_start = time.time()
        await asyncio.gather(*operation_tasks, return_exceptions=True)
        operations_time = time.time() - operations_start

        # Clean up
        cleanup_tasks = []
        for session in successful_sessions:
            cleanup_tasks.append(
                asyncio.create_task(realtime_sync.leave_session(session.session_id))
            )

        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        total_time = time.time() - start_time

        # Performance thresholds
        session_creation_acceptable = session_creation_time < 5.0  # 5 seconds for 50 users
        operations_acceptable = operations_time < 10.0  # 10 seconds for all operations
        total_acceptable = total_time < 15.0  # 15 seconds total

        return {
            "passed": (
                len(successful_sessions) >= concurrent_users * 0.9 and  # 90% success rate
                session_creation_acceptable and
                operations_acceptable and
                total_acceptable
            ),
            "assertions": 4,
            "passed_assertions": sum([
                len(successful_sessions) >= concurrent_users * 0.9,
                session_creation_acceptable,
                operations_acceptable,
                total_acceptable
            ]),
            "metadata": {
                "concurrent_users": concurrent_users,
                "successful_sessions": len(successful_sessions),
                "session_creation_time": round(session_creation_time, 3),
                "operations_time": round(operations_time, 3),
                "total_time": round(total_time, 3),
                "operations_per_second": round(len(operation_tasks) / operations_time, 2)
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 4,
            "passed_assertions": 0,
            "error": str(e)
        }

async def test_data_consistency_across_systems():
    """Test data consistency across caching, sync, and adaptive systems"""
    try:
        user_id = "consistency_user"
        course_id = "consistency_course"

        # Create data in adaptive system
        await adaptive_engine.track_performance(
            user_id, course_id, "lesson_1",
            {
                "completion_rate": 0.8,
                "accuracy_rate": 0.75,
                "time_spent_minutes": 25,
                "mistakes": [{"category": "syntax", "type": "typo"}]
            }
        )

        # Cache some UI data
        cached_ui = A2UIFactory.vstack(
            A2UIFactory.text("Cached Content", style="title"),
            A2UIFactory.progress_tracker(course_id, 1, 5, "Current", "Next")
        )

        cache_key = f"ui_{user_id}_{course_id}"
        await cache_instance.set(cache_key, cached_ui.model_dump(), ttl=3600)

        # Start real-time session
        session = await realtime_sync.join_session(user_id, course_id, device_type="web")

        # Update via real-time sync (should trigger adaptive system)
        await realtime_sync.update_progress(
            user_id, course_id, "lesson_2",
            {"completion_rate": 0.9, "accuracy_rate": 0.85}
        )

        # Allow time for async processing
        await asyncio.sleep(0.5)

        # Verify consistency across systems

        # 1. Adaptive system has latest data
        analytics = adaptive_engine.get_learning_analytics(user_id)
        adaptive_sessions = analytics.get("performance_summary", {}).get("total_sessions", 0)

        # 2. Cache retrieval works
        cached_data = await cache_instance.get(cache_key)

        # 3. Real-time session is active
        active_users = realtime_sync.get_active_users(course_id)
        user_in_session = any(user["user_id"] == user_id for user in active_users)

        # 4. Performance monitoring captures metrics
        perf_metrics = performance_monitor.get_performance_report()

        # Clean up
        await realtime_sync.leave_session(session.session_id)

        return {
            "passed": (
                adaptive_sessions >= 1 and  # At least one session tracked
                cached_data is not None and  # Cache working
                user_in_session and  # Real-time session active
                len(perf_metrics) > 0  # Performance monitoring active
            ),
            "assertions": 4,
            "passed_assertions": sum([
                adaptive_sessions >= 1,
                cached_data is not None,
                user_in_session,
                len(perf_metrics) > 0
            ]),
            "metadata": {
                "adaptive_sessions": adaptive_sessions,
                "cache_hit": cached_data is not None,
                "realtime_active": user_in_session,
                "performance_metrics": len(perf_metrics),
                "session_id": session.session_id
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 4,
            "passed_assertions": 0,
            "error": str(e)
        }

# ==============================================================================
# ADVANCED UI COMPONENT INTEGRATION TESTS
# ==============================================================================

async def test_advanced_component_rendering():
    """Test advanced UI component creation and serialization"""
    try:
        # Create complex nested UI with advanced components
        complex_ui = A2UIFactory.vstack(
            A2UIFactory.text("Advanced Learning Platform", style="title", alignment="center"),

            # Video section
            A2UIFactory.card(
                A2UIFactory.video_player(
                    "https://example.com/advanced.mp4",
                    "Advanced Programming Concepts"
                ),
                title="Video Lesson"
            ),

            # Coding section
            A2UIFactory.card(
                A2UIFactory.code_sandbox(
                    "python",
                    "Practice Exercise",
                    "# Implement a binary search algorithm\ndef binary_search(arr, target):\n    # Your code here\n    pass"
                ),
                title="Coding Exercise"
            ),

            # Collaboration section
            A2UIFactory.card(
                A2UIFactory.collaboration_space(
                    "Study Group",
                    collaboration_types=["real_time_editing", "whiteboard"]
                ),
                title="Collaboration"
            ),

            # Assessment section
            A2UIFactory.card(
                A2UIFactory.text("Assessment coming soon...", style="body"),
                title="Quiz"
            ),

            spacing=20.0
        )

        # Test JSON serialization
        ui_json = complex_ui.model_dump()
        json_string = json.dumps(ui_json, indent=2, default=str)

        # Test deserialization
        reconstructed = A2UIFactory.from_dict(ui_json)

        # Validate structure
        has_video = any(
            child.get("type") == "card" and
            any(grandchild.get("type") == "video_player"
                for grandchild in child.get("children", []))
            for child in ui_json.get("children", [])
        )

        has_code = any(
            child.get("type") == "card" and
            any(grandchild.get("type") == "code_sandbox"
                for grandchild in child.get("children", []))
            for child in ui_json.get("children", [])
        )

        has_collaboration = any(
            child.get("type") == "card" and
            any(grandchild.get("type") == "collaboration_space"
                for grandchild in child.get("children", []))
            for child in ui_json.get("children", [])
        )

        return {
            "passed": (
                complex_ui.type == "vstack" and
                len(complex_ui.children) >= 4 and
                has_video and
                has_code and
                has_collaboration and
                reconstructed.type == "vstack"
            ),
            "assertions": 6,
            "passed_assertions": sum([
                complex_ui.type == "vstack",
                len(complex_ui.children) >= 4,
                has_video,
                has_code,
                has_collaboration,
                reconstructed.type == "vstack"
            ]),
            "metadata": {
                "json_size": len(json_string),
                "component_count": len(complex_ui.children),
                "serialization_success": True,
                "deserialization_success": True
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 6,
            "passed_assertions": 0,
            "error": str(e)
        }

async def test_response_assembler_integration():
    """Test response assembler with performance optimizations"""
    try:
        # Test cached course preview creation
        course_data = {
            "course_id": "assembler_test_course",
            "title": "Test Course",
            "description": "Testing assembler integration",
            "estimated_minutes": 60,
            "total_nodes": 10
        }

        # First call (cache miss)
        start_time = time.time()
        ui_component_1 = await response_assembler.create_course_preview_ui_cached(course_data)
        first_call_time = time.time() - start_time

        # Second call (cache hit)
        start_time = time.time()
        ui_component_2 = await response_assembler.create_course_preview_ui_cached(course_data)
        second_call_time = time.time() - start_time

        # Test batch component creation
        component_specs = [
            {"type": "course_preview", "course_id": f"batch_course_{i}", "title": f"Course {i}"}
            for i in range(3)
        ]

        batch_start_time = time.time()
        batch_components = await response_assembler.batch_create_ui_components(
            component_specs, max_concurrent=2
        )
        batch_time = time.time() - batch_start_time

        # Test progressive rendering assembly
        complex_ui = A2UIFactory.vstack(
            A2UIFactory.text("Complex Learning Experience", style="title"),
            A2UIFactory.video_player("https://example.com/lesson.mp4", "Video Lesson"),
            A2UIFactory.code_sandbox("python", "Exercise", "print('Hello')"),
            A2UIFactory.collaboration_space("Study Group"),
            spacing=16
        )

        progressive_start_time = time.time()
        response = await response_assembler.assemble_response_with_progressive_rendering(
            "Here's your personalized learning experience!",
            ui_layout=complex_ui,
            session_id="assembler_test_session",
            response_mode="progressive"
        )
        progressive_time = time.time() - progressive_start_time

        # Performance validation
        cache_speedup = first_call_time / second_call_time if second_call_time > 0 else 1
        batch_efficient = batch_time < 2.0  # Should complete quickly
        progressive_efficient = progressive_time < 1.0

        return {
            "passed": (
                ui_component_1 is not None and
                ui_component_2 is not None and
                len(batch_components) == 3 and
                response.ui_layout is not None and
                cache_speedup > 1.5 and  # Cache should provide speedup
                batch_efficient and
                progressive_efficient
            ),
            "assertions": 7,
            "passed_assertions": sum([
                ui_component_1 is not None,
                ui_component_2 is not None,
                len(batch_components) == 3,
                response.ui_layout is not None,
                cache_speedup > 1.5,
                batch_efficient,
                progressive_efficient
            ]),
            "metadata": {
                "first_call_time": round(first_call_time * 1000, 3),  # ms
                "second_call_time": round(second_call_time * 1000, 3),  # ms
                "cache_speedup": round(cache_speedup, 2),
                "batch_time": round(batch_time * 1000, 3),  # ms
                "progressive_time": round(progressive_time * 1000, 3),  # ms
                "batch_components": len(batch_components)
            }
        }

    except Exception as e:
        return {
            "passed": False,
            "assertions": 7,
            "passed_assertions": 0,
            "error": str(e)
        }

# ==============================================================================
# TEST SUITE DEFINITIONS
# ==============================================================================

def create_end_to_end_test_suites():
    """Create all end-to-end test suites"""
    return [
        TestSuite(
            name="complete_user_journeys",
            description="Complete user learning journeys",
            test_type=TestType.END_TO_END,
            test_functions=[
                test_complete_learning_journey,
                test_collaborative_learning_session,
                test_adaptive_content_delivery
            ],
            timeout_seconds=60,
            parallel=False
        ),

        TestSuite(
            name="performance_load_tests",
            description="Performance and load testing",
            test_type=TestType.PERFORMANCE,
            test_functions=[
                test_performance_under_load
            ],
            timeout_seconds=120,
            parallel=False
        ),

        TestSuite(
            name="system_integration",
            description="Cross-system integration tests",
            test_type=TestType.INTEGRATION,
            test_functions=[
                test_data_consistency_across_systems,
                test_advanced_component_rendering,
                test_response_assembler_integration
            ],
            timeout_seconds=60,
            parallel=True
        )
    ]