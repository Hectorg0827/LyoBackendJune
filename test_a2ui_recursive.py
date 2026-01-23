#!/usr/bin/env python3
"""
Test script for recursive A2UI implementation
"""

import json
import sys
import os

# Add the lyo_app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lyo_app'))

try:
    from lyo_app.chat.schemas.a2ui_recursive import A2UIFactory, UIComponent
    from lyo_app.chat.assembler import ResponseAssembler

    def test_basic_components():
        """Test basic component creation"""
        print("🧪 Testing basic components...")

        # Test simple components
        text = A2UIFactory.text("Hello World!", style="title")
        button = A2UIFactory.button("Click Me", "test_action", variant="primary")
        divider = A2UIFactory.divider()
        spacer = A2UIFactory.spacer(height=20)

        print(f"✅ Text component: {text.type}")
        print(f"✅ Button component: {button.type}")
        print(f"✅ Divider component: {divider.type}")
        print(f"✅ Spacer component: {spacer.type}")

    def test_nested_components():
        """Test nested component structures"""
        print("\n🧪 Testing nested components...")

        # Create complex nested structure
        ui = A2UIFactory.vstack(
            A2UIFactory.text("Recursive A2UI Demo", style="title"),
            A2UIFactory.card(
                "Weather Card",
                A2UIFactory.hstack(
                    A2UIFactory.text("72°F", style="headline"),
                    A2UIFactory.vstack(
                        A2UIFactory.text("Sunny", style="body"),
                        A2UIFactory.text("Feels like 75°F", style="caption")
                    )
                ),
                A2UIFactory.divider(),
                A2UIFactory.button("Refresh Weather", "refresh_weather", variant="primary")
            ),
            A2UIFactory.spacer(height=16),
            A2UIFactory.text("Powered by Recursive A2UI", style="caption", alignment="center")
        )

        # Convert to JSON
        json_output = json.dumps(ui.model_dump(), indent=2)
        print(f"✅ Nested structure created with {len(json_output)} characters")

        return ui

    def test_assembler_methods():
        """Test ResponseAssembler A2UI factory methods"""
        print("\n🧪 Testing ResponseAssembler factory methods...")

        assembler = ResponseAssembler()

        # Test weather UI
        weather_data = {
            "location": "San Francisco, CA",
            "temp": 72,
            "feels_like": 75,
            "condition": "Sunny",
            "humidity": 65,
            "wind_speed": 12
        }
        weather_ui = assembler.create_weather_ui(weather_data)
        print(f"✅ Weather UI: {weather_ui.type}")

        # Test course overview UI
        course_data = {
            "title": "Python Mastery",
            "description": "Master Python programming from basics to advanced",
            "total_modules": 3,
            "estimated_time": 5,
            "modules": [
                {"id": "1", "title": "Python Basics", "description": "Variables, functions, loops", "lessons": 8, "duration": 45},
                {"id": "2", "title": "Object-Oriented Programming", "description": "Classes, inheritance, polymorphism", "lessons": 10, "duration": 60},
                {"id": "3", "title": "Advanced Topics", "description": "Decorators, generators, async/await", "lessons": 12, "duration": 75}
            ]
        }
        course_ui = assembler.create_course_overview_ui(course_data)
        print(f"✅ Course UI: {course_ui.type}")

        # Test quiz results UI
        quiz_data = {
            "score": 8,
            "total_questions": 10,
            "questions": [
                {
                    "question": "What is the capital of France?",
                    "user_answer": "Paris",
                    "correct_answer": "Paris",
                    "user_correct": True,
                    "explanation": "Paris has been the capital of France since 987 AD."
                }
            ]
        }
        quiz_ui = assembler.create_quiz_results_ui(quiz_data)
        print(f"✅ Quiz UI: {quiz_ui.type}")

        return weather_ui

    def test_json_serialization(ui_component):
        """Test JSON serialization and deserialization"""
        print("\n🧪 Testing JSON serialization...")

        # Serialize to JSON
        json_data = ui_component.model_dump()
        json_string = json.dumps(json_data, indent=2)

        print(f"✅ Serialization successful: {len(json_string)} characters")

        # Test structure validation
        if json_data.get('type') and json_data.get('id'):
            print("✅ JSON structure valid")
        else:
            print("❌ JSON structure invalid")

        # Save to file for inspection
        with open('/tmp/a2ui_test_output.json', 'w') as f:
            f.write(json_string)
        print("✅ JSON saved to /tmp/a2ui_test_output.json")

    def main():
        """Run all tests"""
        print("🚀 Starting Recursive A2UI Backend Tests\n")

        try:
            test_basic_components()
            ui_component = test_nested_components()
            assembler_ui = test_assembler_methods()
            test_json_serialization(assembler_ui)

            print("\n🎉 All tests passed! Backend recursive A2UI implementation is working.")
            return True

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    if __name__ == "__main__":
        success = main()
        sys.exit(0 if success else 1)

except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("Make sure you're running from the LyoBackendJune directory")
    sys.exit(1)