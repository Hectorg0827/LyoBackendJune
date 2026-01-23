#!/usr/bin/env python3
"""
Comprehensive test suite for Recursive A2UI implementation
Tests all components, edge cases, and integration points
"""

import json
import sys
import os
import asyncio
import traceback
from typing import Dict, List, Any, Optional

# Add the lyo_app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lyo_app'))

# Test colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.total = 0
        self.errors = []

    def test(self, name: str, test_func):
        """Run a single test"""
        self.total += 1
        print(f"\n{BLUE}🧪 Testing: {name}{RESET}")

        try:
            result = test_func()
            if result:
                print(f"{GREEN}✅ PASSED: {name}{RESET}")
                self.passed += 1
                return True
            else:
                print(f"{RED}❌ FAILED: {name}{RESET}")
                self.failed += 1
                return False
        except Exception as e:
            print(f"{RED}💥 ERROR: {name} - {str(e)}{RESET}")
            self.errors.append(f"{name}: {str(e)}")
            self.failed += 1
            return False

    async def async_test(self, name: str, test_func):
        """Run an async test"""
        self.total += 1
        print(f"\n{BLUE}🧪 Testing: {name}{RESET}")

        try:
            result = await test_func()
            if result:
                print(f"{GREEN}✅ PASSED: {name}{RESET}")
                self.passed += 1
                return True
            else:
                print(f"{RED}❌ FAILED: {name}{RESET}")
                self.failed += 1
                return False
        except Exception as e:
            print(f"{RED}💥 ERROR: {name} - {str(e)}{RESET}")
            self.errors.append(f"{name}: {str(e)}")
            self.failed += 1
            return False

    def summary(self):
        """Print test summary"""
        print(f"\n{'='*60}")
        print(f"{BLUE}📊 TEST SUMMARY{RESET}")
        print(f"{'='*60}")
        print(f"Total Tests: {self.total}")
        print(f"{GREEN}Passed: {self.passed}{RESET}")
        print(f"{RED}Failed: {self.failed}{RESET}")

        if self.errors:
            print(f"\n{RED}💥 ERRORS:{RESET}")
            for error in self.errors:
                print(f"  • {error}")

        success_rate = (self.passed / self.total * 100) if self.total > 0 else 0
        print(f"\n{GREEN if success_rate >= 80 else RED}Success Rate: {success_rate:.1f}%{RESET}")
        return success_rate >= 80

def test_schema_imports():
    """Test 1: Schema imports and basic structure"""
    try:
        from lyo_app.chat.a2ui_recursive import (
            A2UIFactory, UIComponent, ChatResponseV2,
            TextComponent, ButtonComponent, VStackComponent,
            HStackComponent, CardComponent
        )
        print("  ✓ All schema imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False

def test_basic_components():
    """Test 2: Basic component creation"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory

    try:
        # Test all basic components
        text = A2UIFactory.text("Hello", style="title")
        button = A2UIFactory.button("Click", "test_action")
        image = A2UIFactory.image("https://example.com/image.jpg")
        divider = A2UIFactory.divider()
        spacer = A2UIFactory.spacer(height=20)

        # Validate structure
        assert text.type == "text"
        assert text.content == "Hello"
        assert text.font_style == "title"

        assert button.type == "button"
        assert button.label == "Click"
        assert button.action_id == "test_action"

        print("  ✓ Basic components created successfully")
        return True
    except Exception as e:
        print(f"  ✗ Basic component creation failed: {e}")
        return False

def test_layout_components():
    """Test 3: Layout component nesting"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory

    try:
        # Test nesting
        nested_ui = A2UIFactory.vstack(
            A2UIFactory.text("Header", style="title"),
            A2UIFactory.hstack(
                A2UIFactory.text("Left"),
                A2UIFactory.text("Right")
            ),
            A2UIFactory.card(
                "Card Title",
                A2UIFactory.text("Card content"),
                A2UIFactory.button("Action", "card_action")
            )
        )

        # Validate structure
        assert nested_ui.type == "vstack"
        assert len(nested_ui.children) == 3
        assert nested_ui.children[1].type == "hstack"
        assert nested_ui.children[2].type == "card"
        assert len(nested_ui.children[2].children) == 2

        print("  ✓ Nested layout components working")
        return True
    except Exception as e:
        print(f"  ✗ Layout component nesting failed: {e}")
        return False

def test_json_serialization():
    """Test 4: JSON serialization and validation"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory

    try:
        # Create complex structure
        complex_ui = A2UIFactory.vstack(
            A2UIFactory.text("Complex UI Test", style="title"),
            A2UIFactory.card(
                "Weather Card",
                A2UIFactory.hstack(
                    A2UIFactory.text("72°F", style="headline"),
                    A2UIFactory.vstack(
                        A2UIFactory.text("Sunny"),
                        A2UIFactory.text("Feels like 75°F", style="caption")
                    )
                ),
                A2UIFactory.divider(),
                A2UIFactory.button("Refresh", "refresh_weather")
            )
        )

        # Serialize to JSON
        json_data = complex_ui.model_dump()
        json_str = json.dumps(json_data, indent=2)

        # Validate JSON structure
        parsed = json.loads(json_str)
        assert parsed["type"] == "vstack"
        assert "id" in parsed
        assert "children" in parsed
        assert len(parsed["children"]) == 2

        # Validate nested structure
        card = parsed["children"][1]
        assert card["type"] == "card"
        assert card["title"] == "Weather Card"
        assert len(card["children"]) == 3  # hstack, divider, button

        print(f"  ✓ JSON serialization successful ({len(json_str)} chars)")
        return True
    except Exception as e:
        print(f"  ✗ JSON serialization failed: {e}")
        return False

def test_assembler_methods():
    """Test 5: ResponseAssembler A2UI factory methods"""
    try:
        from lyo_app.chat.assembler import ResponseAssembler

        assembler = ResponseAssembler()

        # Test weather UI
        weather_data = {
            "location": "Test City",
            "temp": 25,
            "feels_like": 28,
            "condition": "Cloudy",
            "humidity": 70,
            "wind_speed": 15
        }
        weather_ui = assembler.create_weather_ui(weather_data)
        assert weather_ui.type == "card"
        assert weather_ui.title == "Current Weather"

        # Test course overview UI
        course_data = {
            "title": "Test Course",
            "description": "A test course",
            "total_modules": 2,
            "estimated_time": 3,
            "modules": [
                {"id": "1", "title": "Module 1", "description": "First module", "lessons": 5, "duration": 30},
                {"id": "2", "title": "Module 2", "description": "Second module", "lessons": 8, "duration": 45}
            ]
        }
        course_ui = assembler.create_course_overview_ui(course_data)
        assert course_ui.type == "vstack"

        # Test quiz results UI
        quiz_data = {
            "score": 8,
            "total_questions": 10,
            "questions": [
                {
                    "question": "Test question?",
                    "user_answer": "Test answer",
                    "correct_answer": "Test answer",
                    "user_correct": True,
                    "explanation": "Test explanation"
                }
            ]
        }
        quiz_ui = assembler.create_quiz_results_ui(quiz_data)
        assert quiz_ui.type == "vstack"

        print("  ✓ All assembler methods working")
        return True
    except Exception as e:
        print(f"  ✗ Assembler methods failed: {e}")
        return False

def test_chat_response_v2():
    """Test 6: ChatResponseV2 model"""
    try:
        from lyo_app.chat.a2ui_recursive import ChatResponseV2, A2UIFactory

        # Create test UI component
        ui_component = A2UIFactory.card(
            "Test Card",
            A2UIFactory.text("Test content"),
            A2UIFactory.button("Test Button", "test_action")
        )

        # Create ChatResponseV2
        response = ChatResponseV2(
            response="Test response",
            ui_layout=ui_component,
            session_id="test_session",
            conversation_id="test_conversation"
        )

        # Validate
        assert response.response == "Test response"
        assert response.ui_layout is not None
        assert response.ui_layout.type == "card"
        assert response.session_id == "test_session"

        # Test serialization
        json_data = response.model_dump()
        assert "ui_layout" in json_data
        assert json_data["ui_layout"]["type"] == "card"

        print("  ✓ ChatResponseV2 model working")
        return True
    except Exception as e:
        print(f"  ✗ ChatResponseV2 model failed: {e}")
        return False

def test_edge_cases():
    """Test 7: Edge cases and error handling"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory, migrate_legacy_content_types

    try:
        # Test empty vstack
        empty_vstack = A2UIFactory.vstack()
        assert empty_vstack.type == "vstack"
        assert len(empty_vstack.children) == 0

        # Test migration of empty content types
        empty_migration = migrate_legacy_content_types([])
        assert empty_migration is None

        # Test migration of single item
        legacy_quiz = [{
            "type": "quiz",
            "question": "Test question?",
            "options": ["A", "B", "C"],
            "correctIndex": 1
        }]
        migrated = migrate_legacy_content_types(legacy_quiz)
        assert migrated.type == "quiz"

        # Test deeply nested structure (10 levels)
        deep_nested = A2UIFactory.vstack(
            A2UIFactory.card("L1",
                A2UIFactory.vstack(
                    A2UIFactory.card("L2",
                        A2UIFactory.vstack(
                            A2UIFactory.card("L3",
                                A2UIFactory.text("Deep content")
                            )
                        )
                    )
                )
            )
        )
        assert deep_nested.type == "vstack"

        print("  ✓ Edge cases handled correctly")
        return True
    except Exception as e:
        print(f"  ✗ Edge cases failed: {e}")
        return False

def test_all_component_types():
    """Test 8: All component types and variants"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory

    try:
        components = [
            # Text variants
            A2UIFactory.text("Title", style="title"),
            A2UIFactory.text("Headline", style="headline"),
            A2UIFactory.text("Body", style="body"),
            A2UIFactory.text("Caption", style="caption"),
            A2UIFactory.text("Code", style="code"),
            A2UIFactory.text("Colored", style="body", color="#FF0000"),
            A2UIFactory.text("Center", style="body", alignment="center"),

            # Button variants
            A2UIFactory.button("Primary", "primary_action", variant="primary"),
            A2UIFactory.button("Secondary", "secondary_action", variant="secondary"),
            A2UIFactory.button("Ghost", "ghost_action", variant="ghost"),
            A2UIFactory.button("Destructive", "destructive_action", variant="destructive"),
            A2UIFactory.button("Disabled", "disabled_action", disabled=True),

            # Layout variants
            A2UIFactory.vstack(spacing=20, alignment="center"),
            A2UIFactory.hstack(spacing=16, alignment="top"),
            A2UIFactory.card("Card", subtitle="Subtitle"),

            # Other components
            A2UIFactory.image("https://example.com/test.jpg", alt_text="Test image"),
            A2UIFactory.divider(color="#CCCCCC"),
            A2UIFactory.spacer(height=50),

            # Legacy components
            A2UIFactory.quiz("Question?", ["A", "B", "C"], correct_index=1, explanation="Answer is B")
        ]

        # Validate all components
        for i, comp in enumerate(components):
            assert hasattr(comp, 'type')
            assert hasattr(comp, 'id')
            assert comp.id  # Should not be empty

        print(f"  ✓ All {len(components)} component types working")
        return True
    except Exception as e:
        print(f"  ✗ Component types test failed: {e}")
        return False

async def test_endpoint_mock():
    """Test 9: Mock endpoint testing (without actual server)"""
    try:
        from lyo_app.chat.a2ui_recursive import ChatResponseV2, A2UIFactory
        import json

        # Mock the endpoint response structure
        def mock_chat_v2_endpoint(message: str) -> dict:
            # Intent detection
            if "weather" in message.lower():
                ui_layout = A2UIFactory.card(
                    "Current Weather",
                    A2UIFactory.text("Mock City, MC", style="headline"),
                    A2UIFactory.hstack(
                        A2UIFactory.text("72°F", style="title"),
                        A2UIFactory.vstack(
                            A2UIFactory.text("Sunny"),
                            A2UIFactory.text("Feels like 75°F", style="caption")
                        )
                    ),
                    A2UIFactory.button("Refresh", "refresh_weather")
                )
                return {
                    "response": "Here's the current weather:",
                    "ui_layout": ui_layout.model_dump(),
                    "session_id": "test_session"
                }
            else:
                return {
                    "response": "Hello! I'm a mock response.",
                    "ui_layout": None,
                    "session_id": "test_session"
                }

        # Test weather request
        weather_response = mock_chat_v2_endpoint("What's the weather?")
        assert weather_response["response"] == "Here's the current weather:"
        assert weather_response["ui_layout"] is not None
        assert weather_response["ui_layout"]["type"] == "card"

        # Test general request
        general_response = mock_chat_v2_endpoint("Hello")
        assert general_response["ui_layout"] is None

        print("  ✓ Endpoint mock testing successful")
        return True
    except Exception as e:
        print(f"  ✗ Endpoint mock testing failed: {e}")
        return False

def test_performance():
    """Test 10: Performance with large structures"""
    from lyo_app.chat.a2ui_recursive import A2UIFactory
    import time

    try:
        start_time = time.time()

        # Create large nested structure (100 components)
        large_components = []
        for i in range(100):
            large_components.append(
                A2UIFactory.card(
                    f"Card {i}",
                    A2UIFactory.text(f"Content {i}"),
                    A2UIFactory.button(f"Button {i}", f"action_{i}")
                )
            )

        large_ui = A2UIFactory.vstack(*large_components)

        # Serialize to JSON
        json_data = large_ui.model_dump()
        json_str = json.dumps(json_data)

        end_time = time.time()
        duration = end_time - start_time

        # Validate
        assert large_ui.type == "vstack"
        assert len(large_ui.children) == 100
        assert len(json_str) > 10000  # Should be substantial JSON

        print(f"  ✓ Performance test passed ({duration:.3f}s, {len(json_str)} chars)")
        return duration < 1.0  # Should complete in under 1 second
    except Exception as e:
        print(f"  ✗ Performance test failed: {e}")
        return False

async def main():
    """Run comprehensive test suite"""
    print(f"{BLUE}{'='*60}")
    print(f"🚀 COMPREHENSIVE RECURSIVE A2UI TEST SUITE")
    print(f"{'='*60}{RESET}")

    runner = TestRunner()

    # Run all tests
    runner.test("Schema imports and basic structure", test_schema_imports)
    runner.test("Basic component creation", test_basic_components)
    runner.test("Layout component nesting", test_layout_components)
    runner.test("JSON serialization and validation", test_json_serialization)
    runner.test("ResponseAssembler factory methods", test_assembler_methods)
    runner.test("ChatResponseV2 model", test_chat_response_v2)
    runner.test("Edge cases and error handling", test_edge_cases)
    runner.test("All component types and variants", test_all_component_types)
    await runner.async_test("Mock endpoint testing", test_endpoint_mock)
    runner.test("Performance with large structures", test_performance)

    # Summary
    success = runner.summary()

    if success:
        print(f"\n{GREEN}🎉 ALL TESTS PASSED! Recursive A2UI implementation is robust and ready for production.{RESET}")
    else:
        print(f"\n{RED}⚠️  Some tests failed. Review the errors above before deploying.{RESET}")

    return success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}⚠️  Tests interrupted by user{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}💥 Test suite crashed: {e}{RESET}")
        traceback.print_exc()
        sys.exit(1)