#!/usr/bin/env python3
"""
Backward Compatibility Test for Recursive A2UI
Ensures existing A2UI systems continue to work alongside new recursive system
"""

import json
import sys
sys.path.append('.')

from lyo_app.chat.a2ui_recursive import (
    ChatResponseV2, migrate_legacy_content_types,
    QuizComponent, CourseRoadmapComponent
)

def test_legacy_content_types_format():
    """Test that legacy content_types format still works"""
    print("🧪 Testing legacy content_types format compatibility...")

    try:
        # Test various legacy content_types formats
        test_cases = [
            # Quiz format
            {
                'type': 'quiz',
                'data': {
                    'question': 'What is Python?',
                    'options': ['A snake', 'A programming language', 'A game'],
                    'correctIndex': 1,
                    'explanation': 'Python is a programming language'
                }
            },
            # Course roadmap format
            {
                'type': 'courseRoadmap',
                'data': {
                    'title': 'Python Learning Path',
                    'modules': [
                        {'name': 'Basics', 'completed': True},
                        {'name': 'Advanced', 'completed': False}
                    ],
                    'totalModules': 2,
                    'completedModules': 1
                }
            },
            # Alternative course roadmap format
            {
                'type': 'course_roadmap',
                'data': {
                    'title': 'JavaScript Path',
                    'modules': [
                        {'name': 'ES6', 'completed': False}
                    ],
                    'totalModules': 1,
                    'completedModules': 0
                }
            },
            # Text format
            {
                'type': 'text',
                'data': {
                    'content': 'Legacy text content',
                    'style': 'body'
                }
            },
            # Text with alternative field names
            {
                'type': 'text',
                'data': {
                    'text': 'Alternative text field',
                    'style': 'caption'
                }
            }
        ]

        for i, content_type in enumerate(test_cases):
            print(f"   Testing legacy format {i+1}: {content_type['type']}")

            # Test migration
            migrated = migrate_legacy_content_types([content_type])

            if migrated is None:
                print(f"     ❌ Migration failed for {content_type['type']}")
                return False

            print(f"     ✅ Migrated to: {migrated.type}")

            # Test JSON serialization
            json_dict = migrated.model_dump()
            json_string = json.dumps(json_dict)
            print(f"     ✅ JSON serialization successful ({len(json_string)} chars)")

        print("✅ All legacy content_types formats work correctly")
        return True

    except Exception as e:
        print(f"❌ Legacy content_types test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chatresponse_v2_backward_compatibility():
    """Test ChatResponseV2 includes all legacy fields"""
    print("\n🧪 Testing ChatResponseV2 backward compatibility...")

    try:
        # Create a ChatResponseV2 with both new and legacy fields
        response = ChatResponseV2(
            response="Test response",
            ui_layout=None,  # New field

            # Legacy fields that should still work
            content_types=[],
            session_id="test-session",
            conversation_id="test-conv",
            response_mode="test",
            quick_explainer={"type": "test"},
            course_proposal={"title": "Test Course"},
            actions=[{"type": "test_action"}],
            suggestions=["Try this", "Or this"]
        )

        print(f"✅ ChatResponseV2 created with legacy fields")

        # Convert to JSON
        json_dict = response.model_dump()
        json_string = json.dumps(json_dict)

        # Check that all legacy fields are present
        legacy_fields = [
            'content_types', 'session_id', 'conversation_id',
            'response_mode', 'quick_explainer', 'course_proposal',
            'actions', 'suggestions'
        ]

        for field in legacy_fields:
            if field not in json_dict:
                print(f"❌ Legacy field missing: {field}")
                return False
            print(f"   ✅ Legacy field present: {field}")

        # Check new field is also present
        if 'ui_layout' not in json_dict:
            print(f"❌ New field missing: ui_layout")
            return False
        print(f"   ✅ New field present: ui_layout")

        print(f"✅ ChatResponseV2 maintains full backward compatibility")
        return True

    except Exception as e:
        print(f"❌ ChatResponseV2 compatibility test failed: {e}")
        return False

def test_legacy_component_direct_usage():
    """Test that legacy components can still be used directly"""
    print("\n🧪 Testing direct legacy component usage...")

    try:
        # Test QuizComponent direct usage
        quiz = QuizComponent(
            question="Direct quiz test",
            options=["A", "B", "C"],
            correct_index=1,
            explanation="This is a direct quiz component"
        )

        print(f"✅ QuizComponent direct creation successful")
        print(f"   Type: {quiz.type}")
        print(f"   Question: {quiz.question[:20]}...")

        # Test CourseRoadmapComponent direct usage
        roadmap = CourseRoadmapComponent(
            title="Direct roadmap test",
            modules=[{"name": "Module 1"}],
            total_modules=1,
            completed_modules=0
        )

        print(f"✅ CourseRoadmapComponent direct creation successful")
        print(f"   Type: {roadmap.type}")
        print(f"   Title: {roadmap.title}")

        # Test JSON serialization
        quiz_json = quiz.model_dump_json()
        roadmap_json = roadmap.model_dump_json()

        print(f"✅ Legacy components JSON serialization successful")
        print(f"   Quiz JSON: {len(quiz_json)} chars")
        print(f"   Roadmap JSON: {len(roadmap_json)} chars")

        return True

    except Exception as e:
        print(f"❌ Direct legacy component test failed: {e}")
        return False

def test_mixed_legacy_and_recursive():
    """Test mixing legacy and recursive components"""
    print("\n🧪 Testing mixed legacy and recursive components...")

    try:
        from lyo_app.chat.a2ui_recursive import A2UIFactory

        # Create a mixed structure: recursive container with legacy content
        mixed_ui = A2UIFactory.vstack(
            A2UIFactory.text("Mixed Content Test", style="title"),

            # Legacy quiz component
            QuizComponent(
                question="Legacy quiz in recursive container",
                options=["Option 1", "Option 2"],
                correct_index=0
            ),

            A2UIFactory.card(
                A2UIFactory.text("This card contains legacy roadmap", style="body"),

                # Legacy roadmap component
                CourseRoadmapComponent(
                    title="Legacy roadmap in recursive card",
                    modules=[{"name": "Test Module"}],
                    total_modules=1,
                    completed_modules=0
                ),

                title="Mixed Content Card"
            ),

            A2UIFactory.text("End of mixed content", style="caption")
        )

        print(f"✅ Mixed UI structure created successfully")
        print(f"   Type: {mixed_ui.type}")
        print(f"   Children: {len(mixed_ui.children)}")

        # Convert to JSON
        json_dict = mixed_ui.model_dump()
        json_string = json.dumps(json_dict, indent=2)

        print(f"✅ Mixed UI JSON serialization successful ({len(json_string)} chars)")

        # Count different component types
        def count_types(component, counts=None):
            if counts is None:
                counts = {}

            comp_type = component.get('type', 'unknown')
            counts[comp_type] = counts.get(comp_type, 0) + 1

            children = component.get('children', [])
            for child in children:
                count_types(child, counts)

            return counts

        type_counts = count_types(json_dict)
        print(f"✅ Component type distribution: {type_counts}")

        # Should have both recursive and legacy types
        has_recursive = any(t in type_counts for t in ['vstack', 'card', 'text'])
        has_legacy = any(t in type_counts for t in ['quiz', 'course_roadmap'])

        if has_recursive and has_legacy:
            print(f"✅ Successfully mixed recursive and legacy components")
            return True
        else:
            print(f"❌ Missing component types - recursive: {has_recursive}, legacy: {has_legacy}")
            return False

    except Exception as e:
        print(f"❌ Mixed component test failed: {e}")
        return False

def test_api_endpoint_backward_compatibility():
    """Test that v1 and v2 endpoints can coexist"""
    print("\n🧪 Testing API endpoint backward compatibility...")

    try:
        # Test that both response models can be created
        from lyo_app.api.v1.chat import ChatResponse

        # Legacy ChatResponse (using correct field names)
        legacy_response = ChatResponse(
            response="Legacy response",
            conversation_id="legacy-conv"
        )

        # Import here to avoid circular import issues
        from lyo_app.chat.a2ui_recursive import A2UIFactory

        # New ChatResponseV2
        new_response = ChatResponseV2(
            response="New recursive response",
            ui_layout=A2UIFactory.text("New recursive text"),
            session_id="new-session"
        )

        print(f"✅ Both response models can be created")
        print(f"   Legacy response text: {legacy_response.response[:20]}...")
        print(f"   New response text: {new_response.response[:20]}...")

        # Test JSON serialization
        legacy_json = legacy_response.model_dump_json()
        new_json = new_response.model_dump_json()

        print(f"✅ Both response models serialize to JSON")
        print(f"   Legacy JSON: {len(legacy_json)} chars")
        print(f"   New JSON: {len(new_json)} chars")

        return True

    except Exception as e:
        print(f"❌ API endpoint compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 BACKWARD COMPATIBILITY TEST SUITE")
    print("=" * 60)

    tests = [
        ("Legacy Content Types Format", test_legacy_content_types_format),
        ("ChatResponseV2 Legacy Fields", test_chatresponse_v2_backward_compatibility),
        ("Direct Legacy Components", test_legacy_component_direct_usage),
        ("Mixed Legacy + Recursive", test_mixed_legacy_and_recursive),
        ("API Endpoint Coexistence", test_api_endpoint_backward_compatibility)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"🧪 Running: {test_name}")
        print(f"{'=' * 60}")

        try:
            if test_func():
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")

    print(f"\n{'=' * 60}")
    print(f"📊 BACKWARD COMPATIBILITY RESULTS")
    print(f"{'=' * 60}")
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")

    if passed == total:
        print(f"\n🎉 ALL BACKWARD COMPATIBILITY TESTS PASSED!")
        print(f"✅ Legacy content_types format still works")
        print(f"✅ ChatResponseV2 maintains all legacy fields")
        print(f"✅ Direct legacy component usage works")
        print(f"✅ Mixed legacy/recursive components work")
        print(f"✅ V1 and V2 API endpoints can coexist")
        print(f"✅ Zero breaking changes for existing systems!")
    else:
        print(f"\n⚠️  Some backward compatibility tests failed!")
        print(f"💡 Review failed tests to ensure no breaking changes")

    return passed == total

if __name__ == "__main__":
    main()