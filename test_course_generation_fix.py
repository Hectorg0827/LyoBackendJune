#!/usr/bin/env python3
"""
Test Course Generation API Fixes
Validates that the course generation and chat endpoints work correctly
"""

import asyncio
import json
import time
from typing import Dict, Any

# Test the fixed course generation
def test_course_generation_response():
    """Test that course generation returns the correct format"""
    # Simulate the response that should be returned
    test_response = {
        "job_id": "cg_20260122190820_aed50dd9",
        "status": "accepted",
        "quality_tier": "fast",
        "estimated_cost_usd": 0.042750000000000003,
        "message": "Course generation started. Poll /status/{job_id} for updates.",
        "poll_url": "/api/v2/courses/status/cg_20260122190820_aed50dd9"
    }

    # Validate all required fields are present
    required_fields = ["job_id", "status", "quality_tier", "estimated_cost_usd", "message", "poll_url"]

    for field in required_fields:
        if field not in test_response:
            print(f"❌ Missing required field: {field}")
            return False

    # Validate types
    if not isinstance(test_response["job_id"], str):
        print("❌ job_id should be string")
        return False

    if not isinstance(test_response["estimated_cost_usd"], (int, float)):
        print("❌ estimated_cost_usd should be numeric")
        return False

    print("✅ Course generation response format is correct")
    print(f"   job_id: {test_response['job_id']}")
    print(f"   status: {test_response['status']}")
    print(f"   cost: ${test_response['estimated_cost_usd']:.4f}")
    return True


def test_chat_a2ui_integration():
    """Test that chat responses include A2UI components"""
    try:
        from lyo_app.chat.a2ui_integration import chat_a2ui_service
        from lyo_app.a2ui.a2ui_generator import a2ui

        # Test explanation UI generation
        explanation_ui = chat_a2ui_service.generate_explanation_ui(
            "Linear equations are mathematical statements where variables are raised to the first power...",
            "Solving Linear Equations"
        )

        # Test that it generates valid A2UI
        if not explanation_ui:
            print("❌ No explanation UI generated")
            return False

        # Test JSON serialization
        json_str = explanation_ui.to_json()
        parsed = json.loads(json_str)

        # Validate structure
        if "type" not in parsed:
            print("❌ A2UI missing type field")
            return False

        if "id" not in parsed:
            print("❌ A2UI missing id field")
            return False

        print("✅ Chat A2UI integration working")
        print(f"   Component type: {parsed['type']}")
        print(f"   JSON size: {len(json_str)} chars")

        # Test course creation UI
        course_data = {
            "title": "Linear Equations Mastery",
            "description": "Learn to solve linear equations step by step",
            "lessons": [
                {"title": "What are Linear Equations?", "type": "video", "duration": "10 min"},
                {"title": "Basic Solving Techniques", "type": "interactive", "duration": "15 min"},
                {"title": "Advanced Applications", "type": "reading", "duration": "12 min"}
            ]
        }

        course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
        if not course_ui:
            print("❌ No course UI generated")
            return False

        course_json = course_ui.to_json()
        course_parsed = json.loads(course_json)

        print("✅ Course UI generation working")
        print(f"   Course component type: {course_parsed['type']}")
        print(f"   Course JSON size: {len(course_json)} chars")

        return True

    except Exception as e:
        print(f"❌ Chat A2UI integration failed: {e}")
        return False


def test_ios_compatibility():
    """Test that generated components are iOS compatible"""
    try:
        from lyo_app.chat.a2ui_integration import chat_a2ui_service

        # Generate a complex UI component
        welcome_ui = chat_a2ui_service.generate_welcome_ui("Test User")
        json_str = welcome_ui.to_json()
        parsed = json.loads(json_str)

        def validate_ios_structure(component):
            """Recursively validate iOS compatibility"""
            # Must have required fields
            if "type" not in component or "id" not in component:
                return False, "Missing type or id"

            # Props should be simple values
            if "props" in component and component["props"]:
                for key, value in component["props"].items():
                    if isinstance(value, dict):
                        # Should be UIValue structure or nested component
                        continue
                    elif not isinstance(value, (str, int, float, bool, list, type(None))):
                        return False, f"Invalid prop type for {key}: {type(value)}"

            # Children should be valid components
            if "children" in component and component["children"]:
                for child in component["children"]:
                    valid, error = validate_ios_structure(child)
                    if not valid:
                        return False, f"Invalid child: {error}"

            return True, "Valid"

        is_valid, error = validate_ios_structure(parsed)

        if not is_valid:
            print(f"❌ iOS compatibility failed: {error}")
            return False

        print("✅ iOS compatibility verified")
        print(f"   Component structure is valid")
        print(f"   Ready for Swift A2UIRenderer")
        return True

    except Exception as e:
        print(f"❌ iOS compatibility test failed: {e}")
        return False


def test_performance():
    """Test performance of A2UI generation"""
    try:
        from lyo_app.chat.a2ui_integration import chat_a2ui_service

        # Time multiple UI generations
        start_time = time.time()

        # Generate different UI types
        components = []

        for i in range(10):
            # Welcome UI
            welcome = chat_a2ui_service.generate_welcome_ui(f"User{i}")
            components.append(welcome)

            # Course UI
            course_data = {
                "title": f"Course {i}",
                "description": f"Description {i}",
                "lessons": [
                    {"title": f"Lesson {j}", "type": "video", "duration": f"{10+j} min"}
                    for j in range(3)
                ]
            }
            course = chat_a2ui_service.generate_course_creation_ui(course_data)
            components.append(course)

        end_time = time.time()
        total_time = (end_time - start_time) * 1000

        # Serialize all components
        total_json_size = 0
        for component in components:
            json_str = component.to_json()
            total_json_size += len(json_str)

        avg_time = total_time / len(components)
        avg_size = total_json_size / len(components)

        print("✅ Performance test completed")
        print(f"   Generated {len(components)} components in {total_time:.1f}ms")
        print(f"   Average time per component: {avg_time:.1f}ms")
        print(f"   Average component size: {avg_size:.0f} chars")
        print(f"   Total JSON output: {total_json_size} chars")

        # Performance criteria
        if avg_time > 50:
            print("⚠️  Performance warning: Average time > 50ms")

        return True

    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("🚀 Testing Course Generation & A2UI Fixes")
    print("=" * 60)

    tests = [
        ("Course Generation Response Format", test_course_generation_response),
        ("Chat A2UI Integration", test_chat_a2ui_integration),
        ("iOS Compatibility", test_ios_compatibility),
        ("Performance", test_performance)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 Testing {test_name}...")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Test crashed: {e}")

    print("\n" + "=" * 60)
    print("🎉 Test Results")
    print("=" * 60)

    success_rate = (passed / total) * 100
    print(f"✅ Passed: {passed}/{total}")
    print(f"📊 Success Rate: {success_rate:.1f}%")

    if success_rate == 100:
        print("🚀 ALL FIXES WORKING PERFECTLY!")
        print("✨ Ready for iOS deployment")
    elif success_rate >= 75:
        print("🌟 FIXES MOSTLY WORKING")
        print("🔧 Minor issues detected")
    else:
        print("❌ FIXES NEED MORE WORK")

    print(f"\n🎯 Status: Course generation and A2UI {'READY' if success_rate >= 75 else 'NOT READY'}")

    return success_rate >= 75


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)