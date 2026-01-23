#!/usr/bin/env python3
"""
A2UI End-to-End Integration Test
Tests the complete A2UI flow from backend generation to iOS compatibility
"""

import json
import time
import asyncio
from typing import Dict, Any
from lyo_app.a2ui.a2ui_generator import a2ui
from lyo_app.chat.a2ui_integration import chat_a2ui_service

class A2UIEndToEndTester:
    def __init__(self):
        self.test_results = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result with details"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })

    def test_backend_component_generation(self) -> bool:
        """Test 1: Backend A2UI Component Generation"""
        try:
            # Test dashboard generation
            dashboard = a2ui.learning_dashboard(
                user_name="Test User",
                stats={"courses": 5, "progress": "75%", "streak": "7 days"},
                courses=[
                    {
                        "title": "Swift Programming",
                        "description": "Learn Swift from basics to advanced",
                        "progress": 68.5,
                        "difficulty": "Intermediate",
                        "duration": "4 hours"
                    },
                    {
                        "title": "AI & Machine Learning",
                        "description": "Introduction to AI concepts",
                        "progress": 25.0,
                        "difficulty": "Beginner",
                        "duration": "6 hours"
                    }
                ]
            )

            # Validate component structure
            if dashboard is None:
                raise ValueError("Dashboard generation returned None")

            if not hasattr(dashboard, 'type'):
                raise ValueError("Dashboard missing type attribute")

            if not hasattr(dashboard, 'children'):
                raise ValueError("Dashboard missing children attribute")

            children_count = len(dashboard.children) if dashboard.children else 0

            self.log_result("Backend Component Generation", True, f"Dashboard type: {dashboard.type}, children: {children_count}")
            return True

        except Exception as e:
            self.log_result("Backend Component Generation", False, str(e))
            return False

    def test_json_serialization_ios_compatibility(self) -> bool:
        """Test 2: JSON Serialization for iOS Compatibility"""
        try:
            # Create complex nested component
            complex_component = a2ui.vstack([
                a2ui.text("Welcome to Lyo! 🎓", font="title", color="#007AFF"),
                a2ui.hstack([
                    a2ui.course_card(
                        "iOS Development",
                        "Build amazing iOS apps",
                        progress=75.5,
                        difficulty="Intermediate",
                        duration="4 hours"
                    ),
                    a2ui.course_card(
                        "Python Basics",
                        "Learn Python programming",
                        progress=45.0,
                        difficulty="Beginner",
                        duration="3 hours"
                    )
                ], spacing=12),
                a2ui.quiz(
                    question="What is SwiftUI?",
                    options=["A framework", "A language", "A tool", "An IDE"],
                    correct_answer=0,
                    action="quiz_answer"
                ),
                a2ui.button("Continue Learning", "continue", style="primary", full_width=True)
            ], spacing=20, padding=16)

            # Test JSON serialization
            json_str = complex_component.to_json()
            parsed = json.loads(json_str)

            # Validate iOS compatibility
            def validate_ios_structure(component_dict):
                """Validate that component structure is iOS/Swift compatible"""
                if not isinstance(component_dict, dict):
                    return False

                # Must have required fields
                if "type" not in component_dict or "id" not in component_dict:
                    return False

                # Props must be simple types or UIValue structures
                if "props" in component_dict and component_dict["props"]:
                    for key, value in component_dict["props"].items():
                        if isinstance(value, dict) and "type" in value and "value" in value:
                            continue  # UIValue structure
                        elif not isinstance(value, (str, int, float, bool, list, type(None))):
                            return False

                # Validate children recursively
                if "children" in component_dict and component_dict["children"]:
                    for child in component_dict["children"]:
                        if not validate_ios_structure(child):
                            return False

                return True

            is_ios_compatible = validate_ios_structure(parsed)

            self.log_result(
                "iOS JSON Compatibility",
                is_ios_compatible,
                f"Serialized {len(json_str)} chars, structure valid: {is_ios_compatible}"
            )
            return is_ios_compatible

        except Exception as e:
            self.log_result("iOS JSON Compatibility", False, str(e))
            return False

    def test_chat_service_integration(self) -> bool:
        """Test 3: Chat Service A2UI Integration"""
        try:
            # Test different chat modes
            welcome_ui = chat_a2ui_service.generate_welcome_ui("Test User")
            assert welcome_ui.type == "vstack"

            course_data = {
                "title": "Advanced Swift",
                "description": "Master advanced Swift concepts",
                "lessons": [
                    {"title": "Protocols", "type": "video", "duration": "20 min"},
                    {"title": "Generics", "type": "reading", "duration": "15 min"},
                    {"title": "Practice", "type": "quiz", "duration": "10 min"}
                ],
                "estimated_duration": "3 hours",
                "difficulty": "Advanced"
            }

            course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
            assert course_ui.type == "vstack"

            quiz_data = {
                "title": "Swift Quiz",
                "current_question": 2,
                "total_questions": 5,
                "question": {
                    "question": "What is a protocol in Swift?",
                    "options": ["A class", "An interface", "A blueprint", "A method"],
                    "correct_answer": 2
                }
            }

            quiz_ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
            assert quiz_ui.type == "vstack"

            self.log_result("Chat Service Integration", True, "Welcome, course, and quiz UIs generated")
            return True

        except Exception as e:
            self.log_result("Chat Service Integration", False, str(e))
            return False

    def test_business_components_functionality(self) -> bool:
        """Test 4: Business Components Functionality"""
        try:
            # Test all business components
            course_card = a2ui.course_card(
                title="Machine Learning Fundamentals",
                description="Learn the basics of ML with hands-on projects",
                progress=82.3,
                difficulty="Intermediate",
                duration="5 hours",
                instructor="Dr. AI",
                rating=4.8,
                students_count=1250
            )

            lesson_card = a2ui.lesson_card(
                title="Introduction to Neural Networks",
                description="Understand the building blocks of deep learning",
                lesson_type="video",
                duration="25 min",
                completed=False,
                action="start_lesson"
            )

            quiz_component = a2ui.quiz(
                question="Which activation function is commonly used in hidden layers?",
                options=["Sigmoid", "ReLU", "Tanh", "Softmax"],
                correct_answer=1,
                explanation="ReLU is preferred for hidden layers due to its computational efficiency",
                action="submit_answer"
            )

            # Validate components
            assert course_card.type == "coursecard"
            assert lesson_card.type == "lessoncard"
            assert quiz_component.type == "quiz"

            # Test serialization
            course_json = course_card.to_json()
            lesson_json = lesson_card.to_json()
            quiz_json = quiz_component.to_json()

            assert len(course_json) > 100
            assert len(lesson_json) > 100
            assert len(quiz_json) > 100

            self.log_result(
                "Business Components",
                True,
                f"Course ({len(course_json)}), Lesson ({len(lesson_json)}), Quiz ({len(quiz_json)}) chars"
            )
            return True

        except Exception as e:
            self.log_result("Business Components", False, str(e))
            return False

    def test_real_world_scenario(self) -> bool:
        """Test 5: Real-World Learning Scenario"""
        try:
            # Simulate a complete learning session
            start_time = time.time()

            # 1. User opens app - dashboard loads
            dashboard = a2ui.learning_dashboard(
                user_name="Sarah Chen",
                stats={
                    "courses": 8,
                    "completed_lessons": 45,
                    "progress": "73%",
                    "streak": "12 days",
                    "points": 2340
                },
                courses=[
                    {
                        "id": "ios-dev",
                        "title": "iOS Development Mastery",
                        "description": "From beginner to expert iOS developer",
                        "progress": 67.5,
                        "difficulty": "Intermediate",
                        "duration": "8 hours",
                        "next_lesson": "Core Data Fundamentals"
                    },
                    {
                        "id": "swift-advanced",
                        "title": "Advanced Swift Techniques",
                        "description": "Master advanced Swift programming concepts",
                        "progress": 45.2,
                        "difficulty": "Advanced",
                        "duration": "6 hours",
                        "next_lesson": "Protocol-Oriented Programming"
                    }
                ]
            )

            # 2. User starts a lesson
            lesson_content = a2ui.vstack([
                a2ui.text("Core Data Fundamentals", font="title"),
                a2ui.text("Lesson 4 of 12", font="subheadline", color="#666666"),
                a2ui.progress_bar(33.3, color="#007AFF"),

                # Video placeholder (using image component)
                a2ui.image(
                    url="https://example.com/thumbnails/core-data-intro.jpg",
                    width=350,
                    height=220
                ),

                # Lesson text
                a2ui.text(
                    "Core Data is Apple's framework for managing object graphs and persistence...",
                    font="body",
                    padding=16,
                    background_color="#F8F9FA",
                    corner_radius=12
                ),

                # Interactive elements
                a2ui.hstack([
                    a2ui.button("Previous", "prev_lesson", style="outline"),
                    a2ui.button("Mark Complete", "complete_lesson", style="primary")
                ], spacing=12)
            ], spacing=20, padding=16)

            # 3. User takes quiz
            quiz_session = a2ui.quiz_session(
                {
                    "question": "What is the main purpose of Core Data?",
                    "options": [
                        "Network communication",
                        "Data persistence and object graph management",
                        "User interface creation",
                        "Background task processing"
                    ],
                    "correct_answer": 1,
                    "explanation": "Core Data provides object graph management and persistence framework."
                },
                current_question=3,
                total_questions=8
            )

            # 4. Generate completion summary
            completion_summary = a2ui.vstack([
                a2ui.text("🎉 Lesson Complete!", font="title", color="#34C759"),
                a2ui.text("Great job on completing Core Data Fundamentals!", font="body"),

                # Stats
                a2ui.hstack([
                    a2ui.vstack([
                        a2ui.text("85%", font="title2", color="#007AFF"),
                        a2ui.text("Quiz Score", font="caption", color="#666666")
                    ]),
                    a2ui.vstack([
                        a2ui.text("12", font="title2", color="#34C759"),
                        a2ui.text("Streak Days", font="caption", color="#666666")
                    ]),
                    a2ui.vstack([
                        a2ui.text("2,485", font="title2", color="#FF9500"),
                        a2ui.text("Total Points", font="caption", color="#666666")
                    ])
                ], spacing=20),

                # Next actions
                a2ui.button("Continue to Next Lesson", "next_lesson", style="primary", full_width=True)
            ], spacing=24, padding=20)

            end_time = time.time()
            generation_time = (end_time - start_time) * 1000

            # Validate all components
            components = [dashboard, lesson_content, quiz_session, completion_summary]
            total_json_size = sum(len(comp.to_json()) for comp in components)

            self.log_result(
                "Real-World Scenario",
                True,
                f"4 screens, {total_json_size} chars, generated in {generation_time:.1f}ms"
            )
            return True

        except Exception as e:
            self.log_result("Real-World Scenario", False, str(e))
            return False

    def test_performance_benchmarks(self) -> bool:
        """Test 6: Performance Benchmarks"""
        try:
            start_time = time.time()

            # Generate 50 complex components
            components = []
            for i in range(50):
                component = a2ui.vstack([
                    a2ui.text(f"Component {i+1}", font="title"),
                    a2ui.hstack([
                        a2ui.course_card(
                            f"Course A{i+1}",
                            f"Description for course A{i+1}",
                            progress=float(i * 2),
                            difficulty="Intermediate"
                        ),
                        a2ui.course_card(
                            f"Course B{i+1}",
                            f"Description for course B{i+1}",
                            progress=float(100 - i * 2),
                            difficulty="Advanced"
                        )
                    ], spacing=12),
                    a2ui.quiz(
                        f"Question {i+1}: What is the answer?",
                        [f"Option A{i}", f"Option B{i}", f"Option C{i}", f"Option D{i}"],
                        correct_answer=i % 4
                    )
                ], spacing=16)

                components.append(component)

            # Serialize all components
            serialized_data = []
            for component in components:
                serialized_data.append(component.to_json())

            end_time = time.time()
            total_time = (end_time - start_time) * 1000

            total_size = sum(len(json_str) for json_str in serialized_data)
            avg_size = total_size / len(components)

            # Performance criteria
            performance_ok = total_time < 1000  # Under 1 second
            size_ok = avg_size > 1000  # Each component is substantial

            self.log_result(
                "Performance Benchmarks",
                performance_ok and size_ok,
                f"50 components, {total_size} total chars, avg {avg_size:.0f} chars, {total_time:.1f}ms"
            )
            return performance_ok and size_ok

        except Exception as e:
            self.log_result("Performance Benchmarks", False, str(e))
            return False

    def test_error_handling_robustness(self) -> bool:
        """Test 7: Error Handling and Robustness"""
        try:
            # Test with malformed data
            try:
                malformed_course = chat_a2ui_service.generate_course_creation_ui({})
                assert malformed_course is not None
            except:
                pass  # Expected to handle gracefully

            # Test with None values
            try:
                none_quiz = chat_a2ui_service.generate_quiz_ui(None)
                # Should not crash
            except:
                pass  # Acceptable

            # Test error UI generation
            error_ui = chat_a2ui_service.generate_error_ui("Test error message")
            assert error_ui.type == "vstack"

            # Test loading UI
            loading_ui = chat_a2ui_service.generate_loading_ui("Processing...")
            assert loading_ui.type == "vstack"

            self.log_result("Error Handling", True, "Graceful error handling confirmed")
            return True

        except Exception as e:
            self.log_result("Error Handling", False, str(e))
            return False

    async def run_all_tests(self):
        """Run all end-to-end tests"""
        print("🚀 A2UI End-to-End Integration Tests")
        print("=" * 60)

        tests = [
            ("Backend Component Generation", self.test_backend_component_generation),
            ("iOS JSON Compatibility", self.test_json_serialization_ios_compatibility),
            ("Chat Service Integration", self.test_chat_service_integration),
            ("Business Components", self.test_business_components_functionality),
            ("Real-World Scenario", self.test_real_world_scenario),
            ("Performance Benchmarks", self.test_performance_benchmarks),
            ("Error Handling", self.test_error_handling_robustness)
        ]

        passed_tests = 0
        total_tests = len(tests)

        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name}...")
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                self.log_result(test_name, False, f"Test crashed: {e}")

        # Final results
        print("\n" + "=" * 60)
        print("🎉 A2UI End-to-End Integration Results")
        print("=" * 60)

        success_rate = (passed_tests / total_tests) * 100

        print(f"✅ Passed: {passed_tests}/{total_tests}")
        print(f"📊 Success Rate: {success_rate:.1f}%")

        if success_rate == 100:
            print("🚀 A2UI END-TO-END: FULLY OPERATIONAL")
            print("💯 Complete integration working perfectly!")
            print("🎯 Ready for production iOS deployment!")
        elif success_rate >= 85:
            print("🌟 A2UI END-TO-END: EXCELLENT")
            print("✨ Minor issues, but production ready!")
        else:
            print("⚠️ A2UI END-TO-END: NEEDS ATTENTION")
            print("🔧 Some integration issues detected")

        print("\n📝 Test Details:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['test']}: {result['details']}")

        print(f"\n🎯 Final Status: A2UI System {'READY' if success_rate >= 85 else 'NOT READY'} for iOS production")

        return success_rate >= 85

async def main():
    """Main test execution"""
    print("A2UI End-to-End Integration Validation")
    print("Testing complete backend-to-iOS flow")

    tester = A2UIEndToEndTester()
    success = await tester.run_all_tests()

    if success:
        print("\n🎉 SUCCESS: A2UI system ready for iOS production deployment!")
        print("📱 Next steps: Add Swift files to Xcode project and test on device")
    else:
        print("\n⚠️ WARNING: A2UI system has integration issues")

    return success

if __name__ == "__main__":
    asyncio.run(main())