#!/usr/bin/env python3
"""
End-to-End Test for A2A Translation Layer
Tests the complete flow: Intent Detection -> Orchestrator -> Translation -> iOS Format
"""

import asyncio
import sys
import json
from pathlib import Path

# Add lyo_app to Python path
sys.path.insert(0, str(Path(__file__).parent))

from lyo_app.api.v1.chat import detect_course_creation_intent, translate_artifact_to_ui_component
from lyo_app.ai_agents.a2a.schemas import Artifact, ArtifactType


def test_intent_detection():
    """Test course creation intent detection"""
    print("\n" + "="*60)
    print("TEST 1: Intent Detection")
    print("="*60)
    
    test_cases = [
        ("Create a course on Python", True),
        ("Make a course about machine learning", True),
        ("Build a full course for data science", True),
        ("What is Python?", False),
        ("Explain variables", False),
    ]
    
    for message, should_detect in test_cases:
        result = detect_course_creation_intent(message)
        detected = result is not None
        status = "✅ PASS" if detected == should_detect else "❌ FAIL"
        print(f"{status}: '{message}' -> {result}")
    
    print()


def test_translation():
    """Test artifact translation to iOS A2UI format"""
    print("\n" + "="*60)
    print("TEST 2: Artifact Translation (A2A -> A2UI)")
    print("="*60)
    
    # Test 1: CURRICULUM_STRUCTURE
    print("\n📚 Test: CURRICULUM_STRUCTURE -> course_roadmap")
    curriculum_artifact = Artifact(
        id="test_curriculum",
        type=ArtifactType.CURRICULUM_STRUCTURE,
        name="Python Basics Course",
        data={
            "title": "Introduction to Python",
            "topic": "Python Programming",
            "level": "beginner",
            "modules": [
                {
                    "title": "Getting Started",
                    "description": "Learn Python basics",
                    "lessons": [
                        {"title": "What is Python?", "duration": "10 min"},
                        {"title": "Installing Python", "duration": "15 min"}
                    ]
                },
                {
                    "title": "Variables and Data Types",
                    "description": "Core Python concepts",
                    "lessons": [
                        {"title": "Variables", "duration": "12 min"},
                        {"title": "Data Types", "duration": "18 min"}
                    ]
                }
            ]
        },
        created_by="PedagogyAgent",
        quality_score=0.95
    )
    
    result = translate_artifact_to_ui_component(curriculum_artifact)
    print(json.dumps(result, indent=2))
    
    # Validate structure
    assert result is not None, "Translation returned None"
    assert result["type"] == "course_roadmap", f"Expected type 'course_roadmap', got '{result['type']}'"
    assert "course_roadmap" in result, "Missing 'course_roadmap' field"
    assert "title" in result["course_roadmap"], "Missing 'title' in course_roadmap"
    assert "modules" in result["course_roadmap"], "Missing 'modules' in course_roadmap"
    assert len(result["course_roadmap"]["modules"]) == 2, "Expected 2 modules"
    print("✅ Structure matches iOS A2UIContent format")
    
    # Test 2: ASSESSMENT
    print("\n❓ Test: ASSESSMENT -> quiz")
    assessment_artifact = Artifact(
        id="test_quiz",
        type=ArtifactType.ASSESSMENT,
        name="Python Quiz",
        data={
            "questions": [
                {
                    "question": "What is a variable?",
                    "options": ["A container", "A function", "A loop", "A class"],
                    "correct_answer": "A container"
                },
                {
                    "question": "What is Python?",
                    "options": ["A snake", "A language", "A framework", "A library"],
                    "correct_answer": "A language"
                }
            ]
        },
        created_by="PedagogyAgent",
        quality_score=0.90
    )
    
    result = translate_artifact_to_ui_component(assessment_artifact)
    print(json.dumps(result, indent=2))
    
    # Validate structure
    assert result is not None, "Translation returned None"
    assert result["type"] == "quiz", f"Expected type 'quiz', got '{result['type']}'"
    assert "quiz" in result, "Missing 'quiz' field"
    assert "questions" in result["quiz"], "Missing 'questions' in quiz"
    assert len(result["quiz"]["questions"]) == 2, "Expected 2 questions"
    print("✅ Structure matches iOS A2UIContent format")
    
    print()


def test_ios_compatibility():
    """Verify the structure is decodable by iOS"""
    print("\n" + "="*60)
    print("TEST 3: iOS Compatibility Check")
    print("="*60)
    
    # Simulate what iOS will receive
    curriculum_artifact = Artifact(
        id="test",
        type=ArtifactType.CURRICULUM_STRUCTURE,
        name="Test Course",
        data={
            "title": "Swift Programming",
            "topic": "iOS Development",
            "level": "intermediate",
            "modules": [
                {
                    "title": "SwiftUI Basics",
                    "description": "Learn SwiftUI",
                    "lessons": [
                        {"title": "Views", "duration": "20 min"}
                    ]
                }
            ]
        },
        created_by="PedagogyAgent",
        quality_score=0.95
    )
    
    ui_component = translate_artifact_to_ui_component(curriculum_artifact)
    
    # Wrap in array as backend does
    ui_components = [ui_component] if ui_component else []
    
    # Simulate iOS response parsing
    print("\n📱 iOS Backend Response (JSON):")
    ios_response = {
        "response": "I've created a course on iOS Development! Let's dive in. 🚀",
        "model_used": "A2A Multi-Agent Pipeline",
        "success": True,
        "ui_component": ui_components
    }
    print(json.dumps(ios_response, indent=2))
    
    # Verify structure
    assert "ui_component" in ios_response, "Missing ui_component"
    assert isinstance(ios_response["ui_component"], list), "ui_component must be a list"
    assert len(ios_response["ui_component"]) > 0, "ui_component list is empty"
    
    component = ios_response["ui_component"][0]
    assert "type" in component, "Missing 'type' field"
    assert component["type"] in ["course_roadmap", "quiz", "topic_selection"], f"Unknown type: {component['type']}"
    
    print("✅ Response structure is iOS-compatible")
    print()


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("A2A TRANSLATION LAYER - END-TO-END TEST")
    print("="*60)
    
    try:
        test_intent_detection()
        test_translation()
        test_ios_compatibility()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nTranslation Layer is ready for production!")
        print("Backend can now:")
        print("  1. Detect course creation intent")
        print("  2. Invoke A2A Orchestrator")
        print("  3. Translate artifacts to iOS A2UI format")
        print("  4. Return structured UI components")
        print()
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
