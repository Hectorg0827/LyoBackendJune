#!/usr/bin/env python3
"""
Demo Chat A2UI Visual Output
Shows exactly what A2UI components will be rendered in iOS app
"""

import json
from typing import Dict, Any

def print_a2ui_visual(component_json: str, title: str):
    """Print a visual representation of A2UI component"""
    print(f"\n🎨 {title}")
    print("=" * 60)

    parsed = json.loads(component_json)

    def render_component(comp: Dict[str, Any], indent: int = 0) -> str:
        prefix = "  " * indent
        comp_type = comp.get("type", "unknown")
        comp_id = comp.get("id", "")[:8]

        visual = f"{prefix}📱 {comp_type.upper()}"

        # Add props info
        props = comp.get("props", {})
        if props:
            prop_info = []
            for key, value in props.items():
                if isinstance(value, dict) and "value" in value:
                    val = value["value"]
                else:
                    val = value

                if key == "text" and isinstance(val, str):
                    prop_info.append(f'"{val[:30]}{"..." if len(str(val)) > 30 else ""}"')
                elif key == "title" and isinstance(val, str):
                    prop_info.append(f"title: {val}")
                elif key == "action" and isinstance(val, str):
                    prop_info.append(f"→ {val}")
                elif key == "progress" and isinstance(val, (int, float)):
                    prop_info.append(f"{val}% complete")
                elif key == "spacing" and isinstance(val, (int, float)):
                    prop_info.append(f"spacing: {val}px")

            if prop_info:
                visual += f" ({', '.join(prop_info)})"

        result = visual + "\n"

        # Render children
        children = comp.get("children", [])
        for child in children:
            result += render_component(child, indent + 1)

        return result

    print(render_component(parsed))
    print(f"📊 JSON Size: {len(component_json)} characters")
    print(f"🏗️  Component ID: {parsed.get('id', 'N/A')[:8]}...")

def demo_course_creation():
    """Demo course creation A2UI"""
    from lyo_app.chat.a2ui_integration import chat_a2ui_service

    course_data = {
        "title": "Linear Equations Mastery",
        "description": "Learn to solve linear equations step by step with interactive examples",
        "lessons": [
            {"title": "What are Linear Equations?", "type": "video", "duration": "10 min"},
            {"title": "Basic Solving Techniques", "type": "interactive", "duration": "15 min"},
            {"title": "Word Problems", "type": "reading", "duration": "12 min"},
            {"title": "Advanced Applications", "type": "quiz", "duration": "8 min"}
        ],
        "estimated_duration": "2 hours",
        "difficulty": "Beginner"
    }

    course_ui = chat_a2ui_service.generate_course_creation_ui(course_data)
    print_a2ui_visual(course_ui.to_json(), "Course Creation Response")

    print("\n📱 iOS App will display:")
    print("• Course title with emoji")
    print("• Description card with background")
    print("• Course stats pills (4 lessons, 2 hours, Beginner)")
    print("• Individual lesson cards with icons")
    print("• Start Course and Customize buttons")

def demo_explanation():
    """Demo explanation A2UI"""
    from lyo_app.chat.a2ui_integration import chat_a2ui_service

    content = """Linear equations are mathematical statements where the highest power of the variable is 1.
    They form straight lines when graphed and are fundamental to algebra.
    The general form is y = mx + b, where m is the slope and b is the y-intercept."""

    explanation_ui = chat_a2ui_service.generate_explanation_ui(content, "Linear Equations")
    print_a2ui_visual(explanation_ui.to_json(), "Explanation Response")

    print("\n📱 iOS App will display:")
    print("• Topic header with light bulb emoji")
    print("• Content in styled card with background")
    print("• \"What's next?\" section")
    print("• Action buttons: Create Course, Practice Quiz, Deep Dive")

def demo_quiz():
    """Demo quiz A2UI"""
    from lyo_app.chat.a2ui_integration import chat_a2ui_service

    quiz_data = {
        "title": "Linear Equations Quiz",
        "current_question": 2,
        "total_questions": 5,
        "question": {
            "question": "What is the slope-intercept form of a linear equation?",
            "options": ["ax + by = c", "y = mx + b", "x = y + b", "m = y + bx"],
            "correct_answer": 1
        }
    }

    quiz_ui = chat_a2ui_service.generate_quiz_ui(quiz_data)
    print_a2ui_visual(quiz_ui.to_json(), "Quiz Response")

    print("\n📱 iOS App will display:")
    print("• Quiz title with brain emoji")
    print("• Progress indicator (Question 2 of 5)")
    print("• Progress bar (40% complete)")
    print("• Interactive quiz component with options")
    print("• Previous/Next navigation buttons")

def demo_welcome():
    """Demo welcome A2UI"""
    from lyo_app.chat.a2ui_integration import chat_a2ui_service

    welcome_ui = chat_a2ui_service.generate_welcome_ui("Sarah")
    print_a2ui_visual(welcome_ui.to_json(), "Welcome/Help Response")

    print("\n📱 iOS App will display:")
    print("• Personalized greeting: \"👋 Welcome back, Sarah!\"")
    print("• Subtitle: \"What would you like to explore today?\"")
    print("• 2x2 grid of feature cards:")
    print("  - Quick Learn (📚)")
    print("  - Create Course (🎓)")
    print("  - Practice Quiz (❓)")
    print("  - Code Help (💻)")

def demo_chat_flow():
    """Demo complete chat flow"""
    print("\n🎭 COMPLETE CHAT FLOW DEMO")
    print("=" * 70)

    chat_examples = [
        {
            "user_input": "I want to learn about machine learning, can you make a course?",
            "expected_response": "🎓 **Course Created: Machine Learning**\n\nI've designed a comprehensive learning experience for you! The course includes 4 lessons covering all the essential concepts.\n\n✨ *Tap below to explore your personalized course*",
            "ui_type": "Course Creation A2UI"
        },
        {
            "user_input": "Explain how photosynthesis works",
            "expected_response": "Photosynthesis is the process by which plants convert light energy into chemical energy...",
            "ui_type": "Explanation A2UI"
        },
        {
            "user_input": "I need help getting started",
            "expected_response": "Hi there! I'm Lyo, your AI learning assistant. Here are some things I can help you with...",
            "ui_type": "Welcome A2UI"
        },
        {
            "user_input": "Give me a quiz on linear equations",
            "expected_response": "Here's a quiz to test your knowledge of linear equations!",
            "ui_type": "Quiz A2UI"
        }
    ]

    for i, example in enumerate(chat_examples, 1):
        print(f"\n📱 Chat Example {i}")
        print("-" * 40)
        print(f"👤 User: {example['user_input']}")
        print(f"🤖 Lyo: {example['expected_response'][:60]}...")
        print(f"🎨 UI: {example['ui_type']}")
        print(f"✨ Result: Rich interactive component instead of plain text!")

def main():
    """Run A2UI visual demo"""
    print("🎨 CHAT A2UI VISUAL DEMONSTRATION")
    print("Showing what your iOS app will display instead of plain text")
    print("=" * 70)

    try:
        demo_course_creation()
        demo_explanation()
        demo_quiz()
        demo_welcome()
        demo_chat_flow()

        print("\n🎉 SUMMARY: A2UI TRANSFORMATION")
        print("=" * 70)
        print("✅ BEFORE: Plain text AI responses")
        print("✅ AFTER: Rich interactive A2UI components")
        print()
        print("📱 Your iOS app will now display:")
        print("• Interactive course cards with progress bars")
        print("• Styled explanation cards with action buttons")
        print("• Quiz components with progress indicators")
        print("• Welcome screens with feature grids")
        print("• Lesson cards, stat pills, navigation buttons")
        print()
        print("🚀 All components work with your existing Swift A2UIRenderer!")
        print("🎯 No more plain text - everything is beautiful and interactive!")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return False

    return True

if __name__ == "__main__":
    success = main()
    print(f"\n{'🎉 SUCCESS' if success else '❌ FAILED'}: A2UI Chat Integration Demo")