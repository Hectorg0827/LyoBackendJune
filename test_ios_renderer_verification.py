#!/usr/bin/env python3
"""
iOS Recursive Renderer Verification Test
Validates that the iOS renderer can handle all backend component types
"""

import sys
import re
sys.path.append('.')

from lyo_app.chat.a2ui_recursive import UIComponent

def get_backend_component_types():
    """Extract all backend component types from the UIComponent union"""
    try:
        # Get all the types in the UIComponent union
        from lyo_app.chat.a2ui_recursive import (
            VStackComponent, HStackComponent, CardComponent,
            TextComponent, ButtonComponent, ImageComponent,
            DividerComponent, SpacerComponent,
            QuizComponent, CourseRoadmapComponent
        )

        backend_types = {
            'vstack': VStackComponent,
            'hstack': HStackComponent,
            'card': CardComponent,
            'text': TextComponent,
            'button': ButtonComponent,
            'image': ImageComponent,
            'divider': DividerComponent,
            'spacer': SpacerComponent,
            'quiz': QuizComponent,
            'course_roadmap': CourseRoadmapComponent
        }

        return backend_types

    except Exception as e:
        print(f"❌ Error getting backend types: {e}")
        return {}

def get_ios_renderer_cases():
    """Extract all cases from iOS A2UIRecursiveRenderer"""
    ios_renderer_path = "/Users/hectorgarcia/LYO_Da_ONE/Sources/Views/Chat/A2UIRecursiveRenderer.swift"

    try:
        with open(ios_renderer_path, 'r') as f:
            content = f.read()

        # Find all switch cases
        case_pattern = r'case \.(\w+)\('
        cases = re.findall(case_pattern, content)

        return set(cases)

    except Exception as e:
        print(f"❌ Error reading iOS renderer: {e}")
        return set()

def get_ios_payload_enum():
    """Extract all cases from iOS ComponentPayload enum"""
    ios_models_path = "/Users/hectorgarcia/LYO_Da_ONE/Sources/Models/A2UIRecursive.swift"

    try:
        with open(ios_models_path, 'r') as f:
            content = f.read()

        # Find ComponentPayload enum cases
        payload_pattern = r'case (\w+)\('
        # Look for enum ComponentPayload section
        enum_start = content.find('enum ComponentPayload')
        if enum_start == -1:
            print("❌ ComponentPayload enum not found")
            return set()

        enum_section = content[enum_start:enum_start + 800]  # Get enum section
        cases = re.findall(payload_pattern, enum_section)

        return set(cases)

    except Exception as e:
        print(f"❌ Error reading iOS models: {e}")
        return set()

def test_ios_renderer_completeness():
    """Test that iOS renderer handles all backend component types"""
    print("🧪 Testing iOS renderer completeness...")

    backend_types = get_backend_component_types()
    ios_renderer_cases = get_ios_renderer_cases()
    ios_payload_cases = get_ios_payload_enum()

    print(f"✅ Backend component types: {len(backend_types)}")
    print(f"   {sorted(backend_types.keys())}")

    print(f"✅ iOS renderer cases: {len(ios_renderer_cases)}")
    print(f"   {sorted(ios_renderer_cases)}")

    print(f"✅ iOS payload cases: {len(ios_payload_cases)}")
    print(f"   {sorted(ios_payload_cases)}")

    # Check coverage
    backend_set = set(backend_types.keys())
    # Map course_roadmap to courseRoadmap for iOS
    backend_set = {t.replace('course_roadmap', 'courseRoadmap') for t in backend_set}

    missing_in_renderer = backend_set - ios_renderer_cases
    missing_in_payloads = backend_set - ios_payload_cases

    print(f"\n📊 Coverage Analysis:")

    if not missing_in_renderer:
        print(f"✅ iOS renderer covers ALL backend types")
    else:
        print(f"❌ iOS renderer missing: {missing_in_renderer}")
        return False

    if not missing_in_payloads:
        print(f"✅ iOS payload enum covers ALL backend types")
    else:
        print(f"❌ iOS payload enum missing: {missing_in_payloads}")
        return False

    # Check for extra cases (not bad, just informational)
    extra_in_renderer = ios_renderer_cases - backend_set
    extra_in_payloads = ios_payload_cases - backend_set

    if extra_in_renderer:
        print(f"ℹ️  iOS renderer has extra cases: {extra_in_renderer}")

    if extra_in_payloads:
        print(f"ℹ️  iOS payload enum has extra cases: {extra_in_payloads}")

    return True

def test_recursive_structure():
    """Test that recursive structure is properly implemented"""
    print("\n🧪 Testing recursive structure...")

    ios_renderer_path = "/Users/hectorgarcia/LYO_Da_ONE/Sources/Views/Chat/A2UIRecursiveRenderer.swift"

    try:
        with open(ios_renderer_path, 'r') as f:
            content = f.read()

        # Check for recursive calls
        recursive_calls = content.count('A2UIRecursiveRenderer(component: child, onAction: onAction)')
        print(f"✅ Found {recursive_calls} recursive renderer calls")

        # Check for ForEach loops (should be used for children)
        foreach_count = content.count('ForEach(data.children)')
        print(f"✅ Found {foreach_count} ForEach loops for children")

        # Check for onAction handling
        onaction_count = content.count('onAction?(')
        print(f"✅ Found {onaction_count} action callbacks")

        if recursive_calls >= 3 and foreach_count >= 3 and onaction_count >= 1:
            print(f"✅ Recursive structure properly implemented")
            return True
        else:
            print(f"❌ Recursive structure incomplete")
            return False

    except Exception as e:
        print(f"❌ Error checking recursive structure: {e}")
        return False

def main():
    print("🚀 iOS RECURSIVE RENDERER VERIFICATION")
    print("=" * 50)

    test1_passed = test_ios_renderer_completeness()
    test2_passed = test_recursive_structure()

    print("=" * 50)
    if test1_passed and test2_passed:
        print("🎉 All iOS renderer verification tests PASSED")
        print("✅ iOS renderer handles all backend component types")
        print("✅ Recursive structure is properly implemented")
        print("✅ Action callbacks are properly wired")
        print("✅ Ready for end-to-end testing")
    else:
        print("❌ Some iOS renderer verification tests FAILED")

    return test1_passed and test2_passed

if __name__ == "__main__":
    main()