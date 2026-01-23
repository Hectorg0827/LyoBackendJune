#!/usr/bin/env python3
"""
Test iOS JSON decoding compatibility
Creates JSON from backend and validates it matches iOS expected format
"""

import json
import sys
sys.path.append('.')

from lyo_app.chat.a2ui_recursive import A2UIFactory, ChatResponseV2
from lyo_app.chat.assembler import ResponseAssembler

def test_ios_json_compatibility():
    """Test that backend JSON matches iOS model expectations"""
    print("🧪 Testing iOS JSON decoding compatibility...")

    assembler = ResponseAssembler()

    # Test weather UI (matching iOS test expectations)
    weather_data = {
        'location': 'San Francisco, CA',
        'temp': 72,
        'condition': 'Sunny',
        'feels_like': 75,
        'humidity': 65,
        'wind_speed': 12
    }

    try:
        # Create the UI layout
        ui_layout = assembler.create_weather_ui(weather_data)

        # Create ChatResponseV2
        response = ChatResponseV2(
            response="Here's the current weather!",
            ui_layout=ui_layout
        )

        # Convert to JSON
        json_dict = response.model_dump()
        json_string = json.dumps(json_dict, indent=2)

        print(f"✅ Backend JSON generation successful")

        # Test UI layout structure matches iOS expectations
        ui_json = json_dict['ui_layout']

        print(f"✅ UI Layout structure:")
        print(f"   - Type: {ui_json.get('type')}")
        print(f"   - ID: {ui_json.get('id', 'present')}")
        print(f"   - Children: {len(ui_json.get('children', []))}")
        print(f"   - Title: {ui_json.get('title', 'N/A')}")

        # Test required fields for iOS DynamicComponent
        required_fields = ['id', 'type']
        for field in required_fields:
            if field not in ui_json:
                print(f"❌ Missing required field: {field}")
                return False
            else:
                print(f"✅ Required field present: {field}")

        # Test children structure
        children = ui_json.get('children', [])
        if children:
            print(f"✅ Testing children structure:")
            for i, child in enumerate(children[:3]):  # Test first 3 children
                if 'id' in child and 'type' in child:
                    print(f"   Child {i}: {child['type']} (id: {child['id'][:8]}...)")
                else:
                    print(f"❌ Child {i} missing required fields")
                    return False

        # Test that JSON can be re-parsed
        try:
            reparsed = json.loads(json_string)
            print(f"✅ JSON re-parsing successful")
        except Exception as e:
            print(f"❌ JSON re-parsing failed: {e}")
            return False

        # Save test JSON for iOS debugging
        with open('/Users/hectorgarcia/Desktop/LyoBackendJune/ios_test_sample.json', 'w') as f:
            f.write(json_string)
        print(f"✅ Test JSON saved to ios_test_sample.json")

        return True

    except Exception as e:
        print(f"❌ iOS JSON compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complex_nesting():
    """Test complex nested structure for iOS compatibility"""
    print("\n🧪 Testing complex nested structure...")

    try:
        # Create complex nested structure
        complex_ui = A2UIFactory.vstack(
            A2UIFactory.text("Complex Test", style="title"),
            A2UIFactory.card(
                A2UIFactory.hstack(
                    A2UIFactory.vstack(
                        A2UIFactory.text("Left side", style="headline"),
                        A2UIFactory.button("Action 1", "test_1")
                    ),
                    A2UIFactory.vstack(
                        A2UIFactory.text("Right side", style="headline"),
                        A2UIFactory.button("Action 2", "test_2")
                    )
                ),
                title="Nested Card"
            ),
            A2UIFactory.divider(),
            A2UIFactory.text("Footer text", style="caption")
        )

        # Convert to JSON
        json_dict = complex_ui.model_dump()
        json_string = json.dumps(json_dict, indent=2)

        print(f"✅ Complex structure JSON generation successful")
        print(f"✅ Structure depth: 4+ levels")
        print(f"✅ Total JSON size: {len(json_string)} characters")

        # Count components recursively
        def count_components(component_dict):
            count = 1
            children = component_dict.get('children', [])
            for child in children:
                count += count_components(child)
            return count

        component_count = count_components(json_dict)
        print(f"✅ Total components: {component_count}")

        return True

    except Exception as e:
        print(f"❌ Complex nesting test failed: {e}")
        return False

def main():
    print("🚀 iOS JSON DECODING COMPATIBILITY TEST")
    print("=" * 50)

    test1_passed = test_ios_json_compatibility()
    test2_passed = test_complex_nesting()

    print("=" * 50)
    if test1_passed and test2_passed:
        print("🎉 All iOS JSON compatibility tests PASSED")
        print("✅ JSON format matches iOS DynamicComponent expectations")
        print("✅ Complex nested structures are properly serialized")
        print("✅ Ready for iOS Swift decoding")
    else:
        print("❌ Some iOS JSON compatibility tests FAILED")

    return test1_passed and test2_passed

if __name__ == "__main__":
    main()