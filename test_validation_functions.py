#!/usr/bin/env python3
"""
Test the new validation functions to ensure they prevent future iOS crashes.
"""

import sys
import uuid
import time
from datetime import datetime

# Add current directory to path for imports
sys.path.append('.')

def test_validation_functions():
    """Test the new safe_json_serialize and yield_safe_sse_event functions."""

    print("🔍 Testing Validation Functions")
    print("=" * 50)

    try:
        from lyo_app.api.v1.stream_lyo2 import safe_json_serialize, yield_safe_sse_event

        # Test safe_json_serialize with problematic data
        problematic_data = {
            "uuid": uuid.uuid4(),
            "timestamp": datetime.now(),
            "nested": {
                "another_uuid": uuid.uuid4(),
                "time": time.time()
            }
        }

        # This should work without throwing an exception
        result = safe_json_serialize(problematic_data, "test_event")
        print("✅ safe_json_serialize handles problematic data")

        # Test yield_safe_sse_event
        sse_result = yield_safe_sse_event("test", problematic_data)
        print("✅ yield_safe_sse_event creates safe SSE format")

        # Verify the result is properly formatted
        assert sse_result.startswith("data: ")
        assert sse_result.endswith("\n\n")
        print("✅ SSE format is correct")

        # Test with extremely problematic data
        class UnserializableClass:
            def __init__(self):
                self.circular_ref = self

        extreme_data = {
            "bad_object": UnserializableClass(),
            "nested_bad": {"another_bad": UnserializableClass()}
        }

        try:
            extreme_result = safe_json_serialize(extreme_data, "extreme_test")
            print("✅ Even extreme data handled gracefully")
        except ValueError as e:
            print(f"✅ Extreme data properly rejected with error: {e}")

        print("\n🎉 All validation function tests passed!")
        return True

    except Exception as e:
        print(f"❌ Validation function test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_validation_functions()
    sys.exit(0 if success else 1)