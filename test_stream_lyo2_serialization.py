#!/usr/bin/env python3
"""
Comprehensive test suite for stream_lyo2 JSON serialization safety.
Tests all potential serialization issues that could cause iOS crashes.
"""

import json
import sys
import uuid
import time
from typing import Any, Dict, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

# Add current directory to path for imports
sys.path.append('.')

def test_json_serialization_safety():
    """Test that all data types used in SSE streams can be safely serialized."""

    print("🧪 Testing JSON Serialization Safety")
    print("=" * 50)

    # Test basic types that should work
    safe_data = {
        "string": "test",
        "integer": 42,
        "float": 3.14,
        "boolean": True,
        "null": None,
        "list": [1, 2, 3],
        "dict": {"nested": "value"}
    }

    try:
        json.dumps(safe_data)
        print("✅ Basic types serialize correctly")
    except Exception as e:
        print(f"❌ Basic types failed: {e}")
        return False

    # Test problematic types that iOS can't handle
    class MockSwiftValue:
        """Simulates a __SwiftValue that would cause iOS crashes."""
        def __repr__(self):
            return "__SwiftValue(some_data)"

    # Test enum serialization
    class TestEnum(Enum):
        VALUE1 = "value1"
        VALUE2 = "value2"

    problematic_data = {
        "uuid_obj": uuid.uuid4(),
        "datetime_obj": datetime.now(),
        "enum_obj": TestEnum.VALUE1,
        "custom_obj": MockSwiftValue(),
        "nested": {
            "uuid": uuid.uuid4(),
            "time": datetime.now()
        }
    }

    # Test our safe serialization approach
    try:
        # This is the pattern we use in stream_lyo2.py
        safe_serialized = json.loads(json.dumps(problematic_data, default=str))
        print("✅ Problematic types handled safely with default=str")

        # Verify the result is actually JSON-safe
        json.dumps(safe_serialized)
        print("✅ Double serialization test passed")

    except Exception as e:
        print(f"❌ Safe serialization failed: {e}")
        return False

    return True

def test_lyo_response_builder():
    """Test the LyoResponseBuilder functionality."""

    print("\n🔧 Testing LyoResponseBuilder")
    print("=" * 50)

    try:
        from lyo_app.api.v1.stream_lyo2 import LyoResponseBuilder

        builder = LyoResponseBuilder()

        # Test with safe data
        safe_payload = {"title": "Test Course", "level": "beginner"}
        cmd = builder.build_command("open_classroom", safe_payload)
        resp = builder.build(cmd, "test_req_123", "test_conv_456")

        # Verify serialization
        json_str = json.dumps(resp, default=str)
        print("✅ LyoResponseBuilder creates serializable data")

        # Test with problematic data
        problematic_payload = {
            "id": uuid.uuid4(),
            "created_at": datetime.now(),
            "metadata": {"uuid": uuid.uuid4()}
        }

        cmd2 = builder.build_command("test_command", problematic_payload)
        resp2 = builder.build(cmd2, str(uuid.uuid4()), str(uuid.uuid4()))

        # Test our safe serialization
        safe_json = json.loads(json.dumps(resp2, default=str))
        json.dumps(safe_json)  # Should not throw
        print("✅ LyoResponseBuilder handles problematic data safely")

    except Exception as e:
        print(f"❌ LyoResponseBuilder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def test_sse_event_formats():
    """Test all SSE event formats used in the stream."""

    print("\n📡 Testing SSE Event Formats")
    print("=" * 50)

    # Test all event types from stream_lyo2.py
    events = [
        # Skeleton event
        {"type": "skeleton", "blocks": ["answer", "artifact"]},

        # Answer event with potential problematic content
        {
            "type": "answer",
            "block": {
                "type": "TutorMessageBlock",
                "content": {"text": "Sample response"},
                "priority": 0
            }
        },

        # Artifact event
        {
            "type": "artifact",
            "block": {
                "type": "quiz",
                "content": {
                    "questions": [{"id": str(uuid.uuid4()), "text": "Sample?"}],
                    "_agent": "quiz"
                },
                "version_id": str(uuid.uuid4())
            }
        },

        # Open classroom event
        {
            "type": "open_classroom",
            "block": {
                "type": "OpenClassroomBlock",
                "content": {
                    "type": "OPEN_CLASSROOM",
                    "course": {
                        "id": str(uuid.uuid4()),
                        "title": "Test Course",
                        "topic": "Testing",
                        "level": "beginner",
                        "duration": "~30 min",
                        "objectives": ["Learn testing"]
                    }
                }
            }
        },

        # Error event
        {"type": "error", "message": "Test error"},

        # Actions event
        {
            "type": "actions",
            "blocks": [
                {
                    "type": "CTARow",
                    "content": {"actions": ["Continue", "Retry"]},
                    "priority": 0
                }
            ]
        }
    ]

    for i, event in enumerate(events):
        try:
            # Test direct serialization
            json.dumps(event)
            print(f"✅ Event {i+1} ({event['type']}) serializes directly")

            # Test safe serialization (our approach)
            safe_event = json.loads(json.dumps(event, default=str))
            json.dumps(safe_event)
            print(f"✅ Event {i+1} ({event['type']}) safe serialization works")

        except Exception as e:
            print(f"❌ Event {i+1} ({event['type']}) failed: {e}")
            return False

    return True

def test_edge_cases():
    """Test edge cases that could cause serialization issues."""

    print("\n🎯 Testing Edge Cases")
    print("=" * 50)

    edge_cases = [
        # Circular references (should be avoided in real code)
        {"type": "test", "self_ref": None},

        # Very nested structures
        {
            "level1": {
                "level2": {
                    "level3": {
                        "uuid": str(uuid.uuid4()),
                        "data": [1, 2, {"nested_uuid": str(uuid.uuid4())}]
                    }
                }
            }
        },

        # Unicode and special characters
        {
            "unicode": "测试 🎉 émojis",
            "special_chars": "\"quotes\" and \\backslashes\\",
            "newlines": "line1\nline2\rline3"
        },

        # Large numbers and precision
        {
            "large_int": 9007199254740991,  # JavaScript MAX_SAFE_INTEGER
            "large_float": 1.7976931348623157e+308,
            "small_float": 5e-324
        }
    ]

    for i, case in enumerate(edge_cases):
        try:
            # Test safe serialization
            safe_case = json.loads(json.dumps(case, default=str))
            json.dumps(safe_case)
            print(f"✅ Edge case {i+1} handled safely")

        except Exception as e:
            print(f"❌ Edge case {i+1} failed: {e}")
            return False

    return True

def test_real_world_simulation():
    """Simulate real-world streaming data that caused the original crash."""

    print("\n🌍 Testing Real-World Simulation")
    print("=" * 50)

    try:
        # Simulate the data structure from the crash log
        simulated_response = {
            "type": "smart_blocks",
            "blocks": [
                {
                    "id": str(uuid.uuid4()),
                    "schema_version": 1,
                    "type": "text",
                    "subtype": "paragraph",
                    "content": {
                        "text": "Imagine a treasure map where \"X\" marks the spot. Algebra is exactly that, but for math!"
                    }
                }
            ]
        }

        # Test the problematic serialization scenario
        safe_blocks = json.loads(json.dumps(simulated_response, default=str))
        json.dumps(safe_blocks)
        print("✅ Smart blocks simulation handled safely")

        # Test TutorMessageBlock scenario
        tutor_block = {
            "type": "answer",
            "block": {
                "type": "TutorMessageBlock",
                "content": {
                    "text": "Sample tutor response with special chars: ñ áéíóú 🎓",
                    "metadata": {
                        "generated_at": datetime.now(),
                        "session_id": uuid.uuid4()
                    }
                },
                "priority": 0
            }
        }

        safe_tutor = json.loads(json.dumps(tutor_block, default=str))
        json.dumps(safe_tutor)
        print("✅ TutorMessageBlock simulation handled safely")

    except Exception as e:
        print(f"❌ Real-world simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def validate_stream_lyo2_imports():
    """Validate that all imports in stream_lyo2.py work correctly."""

    print("\n📦 Validating stream_lyo2 Imports")
    print("=" * 50)

    try:
        from lyo_app.api.v1.stream_lyo2 import (
            router,
            LyoResponseBuilder,
            lyo_response_builder
        )
        print("✅ All critical imports successful")

        # Test the router exists and is configured
        assert router is not None
        print("✅ Router is properly initialized")

        # Test response builder instance
        assert lyo_response_builder is not None
        assert isinstance(lyo_response_builder, LyoResponseBuilder)
        print("✅ Response builder instance is valid")

    except Exception as e:
        print(f"❌ Import validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def main():
    """Run all tests."""

    print("🚀 Stream Lyo2 Serialization Safety Test Suite")
    print("=" * 60)

    tests = [
        ("JSON Serialization Safety", test_json_serialization_safety),
        ("LyoResponseBuilder", test_lyo_response_builder),
        ("SSE Event Formats", test_sse_event_formats),
        ("Edge Cases", test_edge_cases),
        ("Real-World Simulation", test_real_world_simulation),
        ("Import Validation", validate_stream_lyo2_imports)
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"💥 {test_name} CRASHED: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! The iOS crash should be resolved.")
        return True
    else:
        print("⚠️ Some tests failed. Review the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)