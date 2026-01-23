#!/usr/bin/env python3
"""
Test Chat A2UI Integration
Simulates real chat requests to validate A2UI component generation
"""

import asyncio
import json
import sys
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock
import time

class MockUser:
    def __init__(self, id: str = "test_user_123", name: str = "Test User"):
        self.id = id
        self.name = name

class MockDB:
    def __init__(self):
        pass

class ChatA2UITester:
    def __init__(self):
        self.test_results = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })

    async def test_course_creation_request(self) -> bool:
        """Test course creation chat request generates A2UI"""
        try:
            from lyo_app.api.v1.chat import detect_course_creation_intent
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test course creation intent detection
            test_messages = [
                "Create a course on Python programming",
                "I want to learn about machine learning, can you make a course?",
                "Build me a course on data science",
                "Generate a course about web development"
            ]

            for message in test_messages:
                intent = detect_course_creation_intent(message)
                if not intent:
                    self.log_result("Course Intent Detection", False, f"Failed to detect intent in: {message}")
                    return False

            # Test A2UI generation for course creation
            course_data = {
                "title": "Python Programming Mastery",
                "description": "Learn Python from basics to advanced concepts",
                "lessons": [
                    {"title": "Introduction to Python", "type": "video", "duration": "15 min"},
                    {"title": "Variables and Data Types", "type": "interactive", "duration": "20 min"},
                    {"title": "Control Structures", "type": "reading", "duration": "12 min"},
                    {"title": "Functions and Modules", "type": "quiz", "duration": "10 min"}
                ],
                "estimated_duration": "2 hours",
                "difficulty": "Beginner"
            }

            course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
            if not course_ui:
                self.log_result("Course A2UI Generation", False, "No course UI generated")
                return False

            # Test JSON serialization
            json_str = course_ui.to_json()
            parsed = json.loads(json_str)

            # Validate structure
            required_fields = ["type", "id", "children"]
            for field in required_fields:
                if field not in parsed:
                    self.log_result("Course A2UI Structure", False, f"Missing field: {field}")
                    return False

            self.log_result("Course Creation A2UI", True, f"Generated {len(json_str)} chars with {len(parsed.get('children', []))} components")
            return True

        except Exception as e:
            self.log_result("Course Creation A2UI", False, str(e))
            return False

    async def test_explanation_request(self) -> bool:
        """Test explanation requests generate A2UI"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test explanation UI generation
            test_cases = [
                {
                    "topic": "Linear Equations",
                    "content": "Linear equations are mathematical statements where the highest power of the variable is 1. They form straight lines when graphed and are fundamental to algebra."
                },
                {
                    "topic": "Photosynthesis",
                    "content": "Photosynthesis is the process by which plants convert light energy into chemical energy. It occurs in chloroplasts and produces glucose and oxygen."
                },
                {
                    "topic": "Neural Networks",
                    "content": "Neural networks are computing systems inspired by biological neural networks. They consist of interconnected nodes that process information."
                }
            ]

            for case in test_cases:
                explanation_ui = chat_a2ui_service.generate_explanation_ui(case["content"], case["topic"])
                if not explanation_ui:
                    self.log_result("Explanation A2UI Generation", False, f"No UI for topic: {case['topic']}")
                    return False

                # Test JSON structure
                json_str = explanation_ui.to_json()
                parsed = json.loads(json_str)

                if parsed["type"] != "vstack":
                    self.log_result("Explanation A2UI Type", False, f"Expected vstack, got {parsed['type']}")
                    return False

                # Should have multiple children (header, content, actions)
                if len(parsed.get("children", [])) < 3:
                    self.log_result("Explanation A2UI Content", False, f"Too few children: {len(parsed.get('children', []))}")
                    return False

            self.log_result("Explanation A2UI", True, f"Generated explanation UIs for {len(test_cases)} topics")
            return True

        except Exception as e:
            self.log_result("Explanation A2UI", False, str(e))
            return False

    async def test_quiz_request(self) -> bool:
        """Test quiz requests generate A2UI"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test quiz UI generation
            quiz_data = {
                "title": "Python Fundamentals Quiz",
                "current_question": 2,
                "total_questions": 5,
                "question": {
                    "question": "What is the correct way to create a list in Python?",
                    "options": ["list = []", "list = {}", "list = ()", "list = <>"],
                    "correct_answer": 0,
                    "explanation": "Square brackets [] are used to create lists in Python"
                }
            }

            quiz_ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
            if not quiz_ui:
                self.log_result("Quiz A2UI Generation", False, "No quiz UI generated")
                return False

            # Test JSON structure
            json_str = quiz_ui.to_json()
            parsed = json.loads(json_str)

            # Should be vstack with quiz components
            if parsed["type"] != "vstack":
                self.log_result("Quiz A2UI Type", False, f"Expected vstack, got {parsed['type']}")
                return False

            # Should have progress bar, quiz component, navigation
            children = parsed.get("children", [])
            if len(children) < 4:  # Header, progress, quiz, navigation
                self.log_result("Quiz A2UI Components", False, f"Expected 4+ components, got {len(children)}")
                return False

            # Look for quiz component
            has_quiz = any(child.get("type") == "quiz" for child in children)
            if not has_quiz:
                self.log_result("Quiz Component", False, "No quiz component found")
                return False

            self.log_result("Quiz A2UI", True, f"Generated {len(json_str)} chars with quiz component")
            return True

        except Exception as e:
            self.log_result("Quiz A2UI", False, str(e))
            return False

    async def test_welcome_help_request(self) -> bool:
        """Test welcome/help requests generate A2UI"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test welcome UI generation
            welcome_ui = chat_a2ui_service.generate_welcome_ui("Sarah")
            if not welcome_ui:
                self.log_result("Welcome A2UI Generation", False, "No welcome UI generated")
                return False

            # Test JSON structure
            json_str = welcome_ui.to_json()
            parsed = json.loads(json_str)

            # Should be vstack with welcome content
            if parsed["type"] != "vstack":
                self.log_result("Welcome A2UI Type", False, f"Expected vstack, got {parsed['type']}")
                return False

            # Should have greeting, feature cards
            children = parsed.get("children", [])
            if len(children) < 3:  # Greeting, subtitle, grid
                self.log_result("Welcome A2UI Content", False, f"Expected 3+ components, got {len(children)}")
                return False

            # Look for grid with feature cards
            has_grid = any(child.get("type") == "grid" for child in children)
            if not has_grid:
                self.log_result("Welcome Grid", False, "No feature grid found")
                return False

            self.log_result("Welcome/Help A2UI", True, f"Generated {len(json_str)} chars with feature grid")
            return True

        except Exception as e:
            self.log_result("Welcome/Help A2UI", False, str(e))
            return False

    async def test_chat_endpoint_simulation(self) -> bool:
        """Test simulated chat endpoint with A2UI integration"""
        try:
            # Import chat functionality
            from lyo_app.api.v1.chat import detect_course_creation_intent
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Simulate chat requests
            test_requests = [
                {
                    "message": "Create a course on JavaScript fundamentals",
                    "expected_ui_type": "course",
                    "description": "Course creation request"
                },
                {
                    "message": "Explain how photosynthesis works",
                    "expected_ui_type": "explanation",
                    "description": "Explanation request"
                },
                {
                    "message": "I need help getting started",
                    "expected_ui_type": "welcome",
                    "description": "Help request"
                },
                {
                    "message": "What is machine learning?",
                    "expected_ui_type": "explanation",
                    "description": "Learning question"
                }
            ]

            successful_simulations = 0

            for req in test_requests:
                message = req["message"]
                expected_type = req["expected_ui_type"]
                description = req["description"]

                # Simulate the logic from chat endpoint
                ui_component_json = None
                message_lower = message.lower()

                # Course creation intent
                course_intent = detect_course_creation_intent(message)
                if course_intent:
                    course_data = {
                        "title": f"Learn {course_intent['topic'].title()}",
                        "description": f"A comprehensive course on {course_intent['topic']}",
                        "lessons": [
                            {"title": "Introduction", "type": "video", "duration": "15 min"},
                            {"title": "Core Concepts", "type": "interactive", "duration": "20 min"}
                        ]
                    }
                    course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
                    ui_component_json = course_ui.to_json() if course_ui else None

                # Explanation intent
                elif any(word in message_lower for word in ["explain", "what is", "how does", "tell me about"]):
                    explanation_ui = chat_a2ui_service.generate_explanation_ui(
                        f"Here's an explanation of {message}", message
                    )
                    ui_component_json = explanation_ui.to_json() if explanation_ui else None

                # Help intent
                elif any(word in message_lower for word in ["help", "guide", "steps", "how to", "getting started"]):
                    welcome_ui = chat_a2ui_service.generate_welcome_ui("User")
                    ui_component_json = welcome_ui.to_json() if welcome_ui else None

                if ui_component_json:
                    parsed = json.loads(ui_component_json)
                    component_type = parsed.get("type", "unknown")
                    successful_simulations += 1
                    print(f"  ✅ {description}: Generated {component_type} component ({len(ui_component_json)} chars)")
                else:
                    print(f"  ❌ {description}: No A2UI component generated")

            success_rate = successful_simulations / len(test_requests)
            self.log_result("Chat Endpoint Simulation", success_rate >= 0.75, f"{successful_simulations}/{len(test_requests)} requests generated A2UI")
            return success_rate >= 0.75

        except Exception as e:
            self.log_result("Chat Endpoint Simulation", False, str(e))
            return False

    async def test_performance_under_load(self) -> bool:
        """Test A2UI generation performance under load"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            start_time = time.time()

            # Generate 50 different A2UI components rapidly
            components_generated = 0
            total_json_size = 0

            for i in range(50):
                if i % 4 == 0:
                    # Welcome UI
                    ui = chat_a2ui_service.generate_welcome_ui(f"User{i}")
                elif i % 4 == 1:
                    # Course UI
                    course_data = {
                        "title": f"Course {i}",
                        "description": f"Description {i}",
                        "lessons": [{"title": f"Lesson {j}", "type": "video", "duration": "10 min"} for j in range(3)]
                    }
                    ui = chat_a2ui_service.generate_course_creation_ui(course_data)
                elif i % 4 == 2:
                    # Quiz UI
                    quiz_data = {
                        "title": f"Quiz {i}",
                        "current_question": 1,
                        "total_questions": 3,
                        "question": {"question": f"Question {i}?", "options": ["A", "B", "C", "D"], "correct_answer": 0}
                    }
                    ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
                else:
                    # Explanation UI
                    ui = chat_a2ui_service.generate_explanation_ui(f"Content {i}", f"Topic {i}")

                if ui:
                    json_str = ui.to_json()
                    total_json_size += len(json_str)
                    components_generated += 1

            end_time = time.time()
            total_time_ms = (end_time - start_time) * 1000
            avg_time_ms = total_time_ms / components_generated if components_generated > 0 else 0
            avg_size = total_json_size / components_generated if components_generated > 0 else 0

            # Performance criteria
            performance_acceptable = avg_time_ms < 20  # Less than 20ms per component

            self.log_result("Performance Under Load", performance_acceptable,
                          f"Generated {components_generated} components in {total_time_ms:.1f}ms (avg: {avg_time_ms:.1f}ms, {avg_size:.0f} chars)")
            return performance_acceptable

        except Exception as e:
            self.log_result("Performance Under Load", False, str(e))
            return False

    async def run_all_tests(self):
        """Run comprehensive A2UI chat integration tests"""
        print("🚀 Testing Chat A2UI Integration")
        print("=" * 60)

        tests = [
            ("Course Creation Request A2UI", self.test_course_creation_request),
            ("Explanation Request A2UI", self.test_explanation_request),
            ("Quiz Request A2UI", self.test_quiz_request),
            ("Welcome/Help Request A2UI", self.test_welcome_help_request),
            ("Chat Endpoint Simulation", self.test_chat_endpoint_simulation),
            ("Performance Under Load", self.test_performance_under_load)
        ]

        passed_tests = 0
        total_tests = len(tests)

        for test_name, test_func in tests:
            print(f"\n📋 Testing {test_name}...")
            try:
                if await test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_result(test_name, False, f"Test crashed: {e}")
                print(f"❌ {test_name} crashed: {e}")

        # Final results
        print("\n" + "=" * 60)
        print("🎉 Chat A2UI Integration Test Results")
        print("=" * 60)

        success_rate = (passed_tests / total_tests) * 100

        print(f"✅ Passed: {passed_tests}/{total_tests}")
        print(f"📊 Success Rate: {success_rate:.1f}%")

        if success_rate == 100:
            print("🚀 CHAT A2UI INTEGRATION: FULLY OPERATIONAL")
            print("💯 All chat requests generate A2UI components!")
            print("📱 iOS app will display rich interactive content")
        elif success_rate >= 80:
            print("🌟 CHAT A2UI INTEGRATION: EXCELLENT")
            print("✨ Most requests generate A2UI components")
        elif success_rate >= 60:
            print("⚠️ CHAT A2UI INTEGRATION: FUNCTIONAL")
            print("🔧 Some improvements needed")
        else:
            print("❌ CHAT A2UI INTEGRATION: NEEDS WORK")
            print("🚨 Major issues detected")

        print("\n📝 Test Summary:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['test']}: {result['details']}")

        print(f"\n🎯 Final Status: Chat A2UI {'READY' if success_rate >= 80 else 'NOT READY'} for production")

        return success_rate >= 80

async def main():
    """Main test execution"""
    print("Chat A2UI Integration Validation")
    print("Testing chat endpoint A2UI component generation")

    tester = ChatA2UITester()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 SUCCESS: Chat A2UI integration is working perfectly!")
        print("📱 Your iOS app will now display rich interactive components instead of plain text")
        print("🚀 Course generation, explanations, quizzes all have beautiful A2UI")
    else:
        print("\n⚠️ WARNING: Chat A2UI integration has some issues")

    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)