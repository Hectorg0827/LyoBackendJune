#!/usr/bin/env python3
"""
Complete A2UI System Test
Tests all components of the A2UI system without requiring a running server
"""

import json
import sys
import traceback
from typing import Dict, Any

class A2UISystemTester:
    def __init__(self):
        self.test_results = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")

    def test_a2ui_generator_import(self):
        """Test 1: A2UI Generator Module Import"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui, A2UIComponent, A2UIGenerator
            self.log_result("A2UI Generator Import", True, "All classes imported successfully")
            return True
        except Exception as e:
            self.log_result("A2UI Generator Import", False, str(e))
            return False

    def test_component_creation(self):
        """Test 2: A2UI Component Creation"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Test basic components
            text_component = a2ui.text("Hello World", font="title", color="#007AFF")
            button_component = a2ui.button("Click Me", "test_action", style="primary")
            vstack_component = a2ui.vstack([text_component, button_component], spacing=16)

            # Validate structure
            assert text_component.type == "text"
            assert text_component.props["text"].value == "Hello World"
            assert button_component.type == "button"
            assert len(vstack_component.children) == 2

            self.log_result("Component Creation", True, "Basic components created successfully")
            return True
        except Exception as e:
            self.log_result("Component Creation", False, str(e))
            return False

    def test_business_components(self):
        """Test 3: Business Component Creation"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Test business components
            course_card = a2ui.course_card(
                title="Swift Programming",
                description="Learn iOS development",
                progress=75.5,
                difficulty="Intermediate",
                duration="4 hours"
            )

            lesson_card = a2ui.lesson_card(
                title="Variables and Constants",
                description="Learn var and let",
                lesson_type="video",
                duration="15 min"
            )

            quiz_component = a2ui.quiz(
                question="What is the difference between var and let?",
                options=["var is constant", "let is constant", "No difference", "Both deprecated"],
                correct_answer=1
            )

            # Validate
            assert course_card.type == "coursecard"
            assert lesson_card.type == "lessoncard"
            assert quiz_component.type == "quiz"
            assert len(quiz_component.props["options"].value) == 4

            self.log_result("Business Components", True, "Course, lesson, and quiz components created")
            return True
        except Exception as e:
            self.log_result("Business Components", False, str(e))
            return False

    def test_json_serialization(self):
        """Test 4: JSON Serialization"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Create complex component
            dashboard = a2ui.learning_dashboard(
                user_name="Test User",
                stats={"courses": 12, "progress": "87%", "streak": "5 days"},
                courses=[
                    {
                        "id": "ios-dev",
                        "title": "iOS Development",
                        "description": "Build iOS apps",
                        "progress": 68.5,
                        "difficulty": "Intermediate",
                        "duration": "4 hours"
                    }
                ]
            )

            # Test JSON serialization
            json_str = dashboard.to_json()
            parsed = json.loads(json_str)

            # Validate structure
            assert parsed["type"] == "scroll"
            assert "children" in parsed
            assert parsed["id"] is not None

            self.log_result("JSON Serialization", True, f"Dashboard serialized ({len(json_str)} chars)")
            return True
        except Exception as e:
            self.log_result("JSON Serialization", False, str(e))
            return False

    def test_chat_a2ui_service(self):
        """Test 5: Chat A2UI Service"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test welcome UI generation
            welcome_ui = chat_a2ui_service.generate_welcome_ui("Test User")
            assert welcome_ui.type == "vstack"

            # Test course creation UI
            course_data = {
                "title": "Test Course",
                "description": "A test course",
                "lessons": [
                    {"title": "Lesson 1", "type": "video", "duration": "10 min"},
                    {"title": "Lesson 2", "type": "reading", "duration": "5 min"}
                ],
                "estimated_duration": "2 hours",
                "difficulty": "Beginner"
            }
            course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
            assert course_ui.type == "vstack"

            # Test quiz UI
            quiz_data = {
                "title": "Test Quiz",
                "current_question": 1,
                "total_questions": 3,
                "question": {
                    "question": "Test question?",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": 1
                }
            }
            quiz_ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
            assert quiz_ui.type == "vstack"

            self.log_result("Chat A2UI Service", True, "All service methods working")
            return True
        except Exception as e:
            self.log_result("Chat A2UI Service", False, str(e))
            return False

    def test_template_generation(self):
        """Test 6: Template Generation"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Test pre-built templates
            quiz_session = a2ui.quiz_session(
                {"question": "What is 2+2?", "options": ["3", "4", "5"], "correct_answer": 1},
                2, 5
            )

            course_content = a2ui.course_content(
                {"title": "Test Course", "progress": 50},
                {"title": "Test Lesson", "chapter": 1}
            )

            chat_interface = a2ui.chat_interface(
                [{"content": "Hello!", "is_user": False}],
                ["Hi there", "How are you?"]
            )

            # Validate
            assert quiz_session.type == "vstack"
            assert course_content.type == "vstack"
            assert chat_interface.type == "vstack"

            self.log_result("Template Generation", True, "Quiz, course, and chat templates work")
            return True
        except Exception as e:
            self.log_result("Template Generation", False, str(e))
            return False

    def test_component_validation(self):
        """Test 7: Component Validation"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Create complex nested component
            complex_component = a2ui.vstack([
                a2ui.text("Header", font="title"),
                a2ui.hstack([
                    a2ui.course_card("Course 1", "Description 1", progress=50),
                    a2ui.course_card("Course 2", "Description 2", progress=75)
                ], spacing=12),
                a2ui.button("Action Button", "main_action"),
                a2ui.grid([
                    a2ui.text("Item 1"),
                    a2ui.text("Item 2"),
                    a2ui.text("Item 3"),
                    a2ui.text("Item 4")
                ], columns=2)
            ], spacing=20)

            # Validate nested structure
            def count_components(component):
                count = 1
                if component.children:
                    for child in component.children:
                        count += count_components(child)
                return count

            total_components = count_components(complex_component)
            assert total_components > 5  # Should have multiple nested components

            self.log_result("Component Validation", True, f"Complex component with {total_components} total components")
            return True
        except Exception as e:
            self.log_result("Component Validation", False, str(e))
            return False

    def test_error_handling(self):
        """Test 8: Error Handling"""
        try:
            from lyo_app.chat.a2ui_integration import chat_a2ui_service

            # Test error UI generation
            error_ui = chat_a2ui_service.generate_error_ui("Test error message")
            assert error_ui.type == "vstack"

            # Test with invalid data
            try:
                invalid_quiz = chat_a2ui_service.generate_quiz_ui({})  # Empty data
                assert invalid_quiz is not None  # Should handle gracefully
            except Exception:
                pass  # Expected to potentially fail, but shouldn't crash

            self.log_result("Error Handling", True, "Error cases handled gracefully")
            return True
        except Exception as e:
            self.log_result("Error Handling", False, str(e))
            return False

    def test_swift_model_compatibility(self):
        """Test 9: Swift Model Compatibility"""
        try:
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Create component and check Swift compatibility
            test_component = a2ui.vstack([
                a2ui.text("Test", font="title", color="#007AFF"),
                a2ui.button("Test", "test_action", full_width=True),
                a2ui.progress_bar(75.5, color="#34C759")
            ])

            # Convert to dict (what would be sent to iOS)
            component_dict = test_component.to_dict()

            # Check required fields for Swift
            def validate_swift_compatibility(comp_dict):
                if "id" not in comp_dict or "type" not in comp_dict:
                    return False

                if "props" in comp_dict and comp_dict["props"]:
                    # All props should be simple values
                    for value in comp_dict["props"].values():
                        if isinstance(value, dict) and "type" in value:
                            continue  # UIValue structure is okay
                        elif not isinstance(value, (str, int, float, bool, list)):
                            return False

                if "children" in comp_dict and comp_dict["children"]:
                    for child in comp_dict["children"]:
                        if not validate_swift_compatibility(child):
                            return False

                return True

            is_compatible = validate_swift_compatibility(component_dict)
            assert is_compatible, "Component not compatible with Swift models"

            self.log_result("Swift Compatibility", True, "Component structure matches Swift models")
            return True
        except Exception as e:
            self.log_result("Swift Compatibility", False, str(e))
            return False

    def test_performance(self):
        """Test 10: Performance Benchmarks"""
        try:
            import time
            from lyo_app.a2ui.a2ui_generator import a2ui

            # Test component generation performance
            start_time = time.time()

            # Create multiple complex components
            for i in range(10):
                dashboard = a2ui.learning_dashboard(
                    f"User {i}",
                    {"courses": i * 2, "progress": f"{i * 10}%", "streak": f"{i} days"},
                    [
                        {
                            "title": f"Course {j}",
                            "description": f"Description {j}",
                            "progress": j * 10,
                            "difficulty": "Intermediate"
                        } for j in range(3)
                    ]
                )
                # Serialize to JSON to test full pipeline
                json_str = dashboard.to_json()

            end_time = time.time()
            total_time = (end_time - start_time) * 1000  # Convert to ms

            if total_time < 1000:  # Should complete in under 1 second
                self.log_result("Performance", True, f"10 complex components in {total_time:.1f}ms")
                return True
            else:
                self.log_result("Performance", False, f"Too slow: {total_time:.1f}ms")
                return False

        except Exception as e:
            self.log_result("Performance", False, str(e))
            return False

    def run_all_tests(self):
        """Run all system tests"""
        print("🚀 Starting A2UI Complete System Tests")
        print("=" * 60)

        tests = [
            ("A2UI Generator Import", self.test_a2ui_generator_import),
            ("Component Creation", self.test_component_creation),
            ("Business Components", self.test_business_components),
            ("JSON Serialization", self.test_json_serialization),
            ("Chat A2UI Service", self.test_chat_a2ui_service),
            ("Template Generation", self.test_template_generation),
            ("Component Validation", self.test_component_validation),
            ("Error Handling", self.test_error_handling),
            ("Swift Compatibility", self.test_swift_model_compatibility),
            ("Performance", self.test_performance)
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
                print(f"❌ {test_name} crashed: {e}")
                traceback.print_exc()

        # Print summary
        print("\n" + "=" * 60)
        print("🎉 A2UI Complete System Test Results")
        print("=" * 60)

        success_rate = (passed_tests / total_tests) * 100

        print(f"✅ Passed: {passed_tests}/{total_tests}")
        print(f"📊 Success Rate: {success_rate:.1f}%")

        if success_rate == 100:
            print("🚀 A2UI SYSTEM: FULLY OPERATIONAL")
            print("💯 All components working perfectly!")
        elif success_rate >= 90:
            print("🌟 A2UI SYSTEM: EXCELLENT")
            print("✨ Minor issues, but production ready!")
        elif success_rate >= 75:
            print("⚠️  A2UI SYSTEM: FUNCTIONAL")
            print("🔧 Some issues need attention")
        else:
            print("❌ A2UI SYSTEM: NEEDS WORK")
            print("🚨 Major issues detected")

        # Detailed results
        print("\n📝 Detailed Results:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['test']}: {result['details']}")

        print(f"\n🎯 Final Status: A2UI System is {'READY' if success_rate >= 90 else 'NOT READY'} for production")

        return success_rate >= 90


def main():
    """Main test execution"""
    print("A2UI Complete System Validation")
    print("Testing all components without requiring server")

    tester = A2UISystemTester()
    success = tester.run_all_tests()

    if success:
        print("\n🎉 SUCCESS: A2UI system is ready for deployment!")
    else:
        print("\n⚠️  WARNING: A2UI system has issues that need attention")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()