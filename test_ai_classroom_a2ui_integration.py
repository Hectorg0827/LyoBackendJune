#!/usr/bin/env python3
"""
AI Classroom + A2UI Integration Test
Tests the complete integration between AI Classroom system and Recursive A2UI
"""

import json
import sys
import asyncio
sys.path.append('.')

from lyo_app.chat.a2ui_recursive import A2UIFactory, ChatResponseV2
from lyo_app.chat.assembler import ResponseAssembler
from lyo_app.api.v1.chat import (
    detect_ai_classroom_intent, generate_ai_classroom_course,
    extract_learning_topic, get_user_learning_progress
)

async def test_intent_detection():
    """Test AI Classroom intent detection"""
    print("🧪 Testing AI Classroom intent detection...")

    test_messages = [
        ("teach me python", "course_creation"),
        ("learn about machine learning", "course_creation"),
        ("continue my lesson", "continue_learning"),
        ("show my progress", "continue_learning"),
        ("I finished the course", "course_completion"),
        ("show available courses", "course_discovery"),
        ("help with algorithms", "general_learning")
    ]

    all_passed = True
    for message, expected_intent in test_messages:
        detected_intent = detect_ai_classroom_intent(message)
        if detected_intent == expected_intent:
            print(f"   ✅ '{message}' -> {detected_intent}")
        else:
            print(f"   ❌ '{message}' -> Expected: {expected_intent}, Got: {detected_intent}")
            all_passed = False

    return all_passed

async def test_topic_extraction():
    """Test learning topic extraction"""
    print("\n🧪 Testing learning topic extraction...")

    test_cases = [
        ("teach me python programming", "python programming"),
        ("I want to learn about machine learning", "machine learning"),
        ("course on data science please", "data science"),
        ("study javascript", "javascript"),
        ("teach me react today", "react")
    ]

    all_passed = True
    for message, expected_topic in test_cases:
        extracted_topic = extract_learning_topic(message)
        if extracted_topic == expected_topic:
            print(f"   ✅ '{message}' -> '{extracted_topic}'")
        else:
            print(f"   ❌ '{message}' -> Expected: '{expected_topic}', Got: '{extracted_topic}'")
            all_passed = False

    return all_passed

async def test_ai_classroom_course_generation():
    """Test AI Classroom course generation with A2UI display"""
    print("\n🧪 Testing AI Classroom course generation...")

    try:
        # Mock user object
        class MockUser:
            def __init__(self):
                self.id = "test-user-123"

        user = MockUser()

        # Test course generation
        course_data = await generate_ai_classroom_course("teach me python", user)

        if not course_data:
            print("   ❌ Course generation returned None")
            return False

        print(f"   ✅ Course generated: {course_data.get('title')}")
        print(f"      Subject: {course_data.get('subject')}")
        print(f"      Duration: {course_data.get('estimated_minutes')} minutes")
        print(f"      Lessons: {course_data.get('total_nodes')}")

        # Test A2UI rendering
        assembler = ResponseAssembler()
        ui_layout = assembler.create_course_preview_ui(course_data)

        if ui_layout and ui_layout.type == "vstack":
            print(f"   ✅ A2UI course preview created: {ui_layout.type}")
            print(f"      Children: {len(ui_layout.children)}")

            # Test JSON serialization
            json_dict = ui_layout.model_dump()
            json_string = json.dumps(json_dict, indent=2)
            print(f"   ✅ JSON serialization successful ({len(json_string)} chars)")

            return True
        else:
            print("   ❌ A2UI course preview creation failed")
            return False

    except Exception as e:
        print(f"   ❌ Course generation test failed: {e}")
        return False

async def test_progress_tracking_ui():
    """Test learning progress UI with A2UI"""
    print("\n🧪 Testing learning progress UI...")

    try:
        # Get mock progress data
        progress_data = await get_user_learning_progress("test-user-123")

        print(f"   ✅ Progress data retrieved: {progress_data.get('course_title')}")
        print(f"      Current: {progress_data.get('current_node')}/{progress_data.get('total_nodes')}")

        # Test A2UI rendering
        assembler = ResponseAssembler()
        ui_layout = assembler.create_learning_progress_ui(progress_data)

        if ui_layout and ui_layout.type == "vstack":
            print(f"   ✅ A2UI progress UI created: {ui_layout.type}")
            print(f"      Children: {len(ui_layout.children)}")

            # Test JSON serialization
            json_dict = ui_layout.model_dump()
            json_string = json.dumps(json_dict, indent=2)
            print(f"   ✅ JSON serialization successful ({len(json_string)} chars)")

            return True
        else:
            print("   ❌ A2UI progress UI creation failed")
            return False

    except Exception as e:
        print(f"   ❌ Progress tracking test failed: {e}")
        return False

async def test_ai_classroom_components():
    """Test AI Classroom specific components"""
    print("\n🧪 Testing AI Classroom A2UI components...")

    try:
        # Test CoursePreview component
        course_preview = A2UIFactory.course_preview(
            course_id="test-course-123",
            title="Python Fundamentals",
            description="Learn Python programming from basics to advanced",
            subject="Python",
            grade_band="Beginner",
            estimated_minutes=120,
            total_nodes=15,
            thumbnail_url="https://example.com/python-course.jpg"
        )

        print(f"   ✅ CoursePreview component: {course_preview.type}")
        print(f"      Course ID: {course_preview.course_id}")
        print(f"      Title: {course_preview.title}")

        # Test ProgressTracker component
        progress_tracker = A2UIFactory.progress_tracker(
            course_title="Python Fundamentals",
            current_node=7,
            total_nodes=15,
            current_node_title="Functions and Modules",
            next_node_title="Object-Oriented Programming"
        )

        print(f"   ✅ ProgressTracker component: {progress_tracker.type}")
        print(f"      Progress: {progress_tracker.completed_percentage}%")

        # Test LearningNode component
        learning_node = A2UIFactory.learning_node(
            node_id="node-123",
            title="Introduction to Variables",
            content="Learn about Python variables and data types",
            node_type="narrative",
            is_current=True,
            estimated_minutes=10
        )

        print(f"   ✅ LearningNode component: {learning_node.type}")
        print(f"      Node Type: {learning_node.node_type}")
        print(f"      Current: {learning_node.is_current}")

        # Test InteractiveLesson component
        interactive_lesson = A2UIFactory.interactive_lesson(
            lesson_id="lesson-456",
            title="Python Syntax Basics",
            content="Interactive lesson on Python syntax and basic operations",
            lesson_type="interactive",
            duration_seconds=600,
            has_quiz=True
        )

        print(f"   ✅ InteractiveLesson component: {interactive_lesson.type}")
        print(f"      Duration: {interactive_lesson.duration_seconds}s")
        print(f"      Has Quiz: {interactive_lesson.has_quiz}")

        return True

    except Exception as e:
        print(f"   ❌ AI Classroom components test failed: {e}")
        return False

async def test_end_to_end_integration():
    """Test complete end-to-end AI Classroom + A2UI flow"""
    print("\n🧪 Testing end-to-end integration...")

    try:
        # Simulate user message: "teach me python"
        user_message = "teach me python"

        # Step 1: Intent detection
        intent = detect_ai_classroom_intent(user_message)
        print(f"   ✅ Step 1 - Intent detected: {intent}")

        # Step 2: Topic extraction
        topic = extract_learning_topic(user_message)
        print(f"   ✅ Step 2 - Topic extracted: {topic}")

        # Step 3: Course generation
        class MockUser:
            def __init__(self):
                self.id = "test-user-123"

        user = MockUser()
        course_data = await generate_ai_classroom_course(user_message, user)
        print(f"   ✅ Step 3 - Course generated: {course_data.get('title')}")

        # Step 4: A2UI rendering
        assembler = ResponseAssembler()
        ui_layout = assembler.create_course_preview_ui(course_data)
        print(f"   ✅ Step 4 - A2UI layout created: {ui_layout.type}")

        # Step 5: ChatResponseV2 creation
        response = ChatResponseV2(
            response=f"I've created a personalized course for you! This course covers {course_data.get('subject')} and should take about {course_data.get('estimated_minutes')} minutes to complete.",
            ui_layout=ui_layout,
            session_id="test-session-456",
            response_mode="course_creation"
        )
        print(f"   ✅ Step 5 - ChatResponseV2 created with UI layout")

        # Step 6: JSON serialization for iOS
        json_dict = response.model_dump()
        json_string = json.dumps(json_dict, indent=2)
        print(f"   ✅ Step 6 - JSON serialization ({len(json_string)} chars)")

        # Step 7: Validate iOS compatibility
        ui_json = json_dict['ui_layout']
        required_fields = ['id', 'type', 'children']
        for field in required_fields:
            if field not in ui_json:
                print(f"   ❌ Step 7 - Missing required field: {field}")
                return False

        print(f"   ✅ Step 7 - iOS compatibility validated")

        return True

    except Exception as e:
        print(f"   ❌ End-to-end integration test failed: {e}")
        return False

async def test_course_completion_flow():
    """Test course completion celebration UI"""
    print("\n🧪 Testing course completion flow...")

    try:
        completion_data = {
            'course_title': 'Python Fundamentals',
            'total_nodes': 15,
            'time_spent': 120,
            'score': 95
        }

        assembler = ResponseAssembler()
        ui_layout = assembler.create_course_completion_ui(completion_data)

        if ui_layout and ui_layout.type == "vstack":
            print(f"   ✅ Course completion UI created: {ui_layout.type}")
            print(f"      Children: {len(ui_layout.children)}")

            # Find congratulations text
            json_dict = ui_layout.model_dump()
            has_celebration = any("Congratulations" in str(child) for child in json_dict.get('children', []))

            if has_celebration:
                print(f"   ✅ Celebration content found")
            else:
                print(f"   ⚠️  No celebration content found")

            return True
        else:
            print("   ❌ Course completion UI creation failed")
            return False

    except Exception as e:
        print(f"   ❌ Course completion test failed: {e}")
        return False

async def main():
    print("🚀 AI CLASSROOM + A2UI INTEGRATION TEST SUITE")
    print("=" * 60)

    tests = [
        ("Intent Detection", test_intent_detection),
        ("Topic Extraction", test_topic_extraction),
        ("Course Generation + A2UI", test_ai_classroom_course_generation),
        ("Progress Tracking UI", test_progress_tracking_ui),
        ("AI Classroom Components", test_ai_classroom_components),
        ("End-to-End Integration", test_end_to_end_integration),
        ("Course Completion Flow", test_course_completion_flow)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"🧪 Running: {test_name}")
        print(f"{'=' * 60}")

        try:
            if await test_func():
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")

    print(f"\n{'=' * 60}")
    print(f"📊 AI CLASSROOM + A2UI INTEGRATION RESULTS")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")

    if passed == total:
        print(f"\n🎉 ALL AI CLASSROOM + A2UI INTEGRATION TESTS PASSED!")
        print(f"✅ Intent detection working correctly")
        print(f"✅ Course generation integrated with A2UI")
        print(f"✅ Progress tracking UI functional")
        print(f"✅ All AI Classroom components working")
        print(f"✅ End-to-end integration successful")
        print(f"✅ Course completion flow working")
        print(f"✅ AI Classroom + A2UI integration is COMPLETE!")
    else:
        print(f"\n⚠️  Some integration tests failed. Review above for details.")

    return passed == total

if __name__ == "__main__":
    asyncio.run(main())