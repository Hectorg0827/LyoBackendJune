#!/usr/bin/env python3
# Test Runner - Comprehensive test execution for Lyo platform
import subprocess
import sys
from pathlib import Path

def run_test_suite(test_type="all"):
    print(f"🧪 Running {test_type} tests...")

    test_commands = {
        "unit": ["python", "-m", "pytest", "lyo_app/", "-v", "--tb=short"],
        "integration": ["python", "test_ai_classroom_a2ui_integration.py"],
        "performance": ["python", "test_performance_optimizations.py"],
        "comprehensive": ["python", "test_comprehensive_quality_assurance.py"],
        "all": ["python", "test_comprehensive_quality_assurance.py"]
    }

    if test_type not in test_commands:
        print(f"❌ Unknown test type: {test_type}")
        print(f"Available types: {list(test_commands.keys())}")
        return False

    try:
        result = subprocess.run(test_commands[test_type],
                              capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print(f"✅ {test_type} tests passed")
            return True
        else:
            print(f"❌ {test_type} tests failed")
            print(f"Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"⏰ {test_type} tests timed out (>5min)")
        return False
    except Exception as e:
        print(f"💥 Error running {test_type} tests: {e}")
        return False

if __name__ == "__main__":
    test_type = sys.argv[1] if len(sys.argv) > 1 else "all"
    success = run_test_suite(test_type)
    sys.exit(0 if success else 1)
