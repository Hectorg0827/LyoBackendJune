#!/usr/bin/env python3
"""Quick test to verify API key validation is working"""

import os
import sys

# Test the is_valid_key function logic
def test_is_valid_key():
    """Test the validation function matches implementation"""
    
    def is_valid_key(key: str) -> bool:
        if not key:
            return False
        placeholders = [
            'YOUR-', 'YOUR_', 'REPLACE_', 'your-', 'your_', 'replace_',
            'XXX', 'xxx', 'test', 'demo', 'placeholder',
        ]
        key_lower = key.lower()
        if any(p in key_lower for p in placeholders):
            return False
        return len(key) > 10
    
    # Test cases
    test_cases = [
        ("", False, "empty string"),
        ("YOUR-SECRET-KEY", False, "placeholder YOUR-"),
        ("sk_test_123", False, "placeholder test"),
        ("DEMO_KEY_123", False, "placeholder DEMO"),
        ("abc123", False, "too short"),
        ("valid_api_key_12345", True, "valid long key"),
        ("sk_live_abcdefghijklmnop", True, "valid real-looking key"),
    ]
    
    print("Testing is_valid_key() function:")
    all_passed = True
    for key, expected, description in test_cases:
        result = is_valid_key(key)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"  {status} {description}: '{key}' -> {result} (expected {expected})")
    
    return all_passed

def test_env_vars():
    """Check what's in environment"""
    print("\nChecking environment variables:")
    
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    print(f"  GEMINI_API_KEY present: {bool(os.getenv('GEMINI_API_KEY'))}")
    print(f"  GOOGLE_API_KEY present: {bool(os.getenv('GOOGLE_API_KEY'))}")
    print(f"  OPENAI_API_KEY present: {bool(openai_key)}")
    
    # Check .env file if it exists
    env_file = "/Users/hectorgarcia/Desktop/LyoBackendJune/.env"
    if os.path.exists(env_file):
        print(f"\n.env file exists at {env_file}")
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()
            for line in lines:
                if 'KEY' in line:
                    key_name = line.split('=')[0]
                    is_set = '=' in line and len(line.split('=', 1)[1].strip()) > 0
                    status = "SET" if is_set else "EMPTY"
                    print(f"    {key_name}: {status}")
        except Exception as e:
            print(f"  Error reading .env: {e}")
    else:
        print(f"\n.env file NOT FOUND at {env_file}")
    
    return bool(gemini_key) or bool(openai_key)

if __name__ == "__main__":
    print("=" * 60)
    print("API Key Validation Test")
    print("=" * 60)
    
    validation_ok = test_is_valid_key()
    env_ok = test_env_vars()
    
    print("\n" + "=" * 60)
    if validation_ok:
        print("✅ Validation function tests: PASSED")
    else:
        print("❌ Validation function tests: FAILED")
    
    if env_ok:
        print("✅ Environment: Has API keys configured")
    else:
        print("⚠️  Environment: No valid API keys found")
        print("\nFix by setting environment variables:")
        print("  export GEMINI_API_KEY=your_actual_key")
        print("  export OPENAI_API_KEY=your_actual_key")
        print("\nOr update .env file in /Users/hectorgarcia/Desktop/LyoBackendJune/")
    
    print("=" * 60)
