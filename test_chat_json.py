#!/usr/bin/env python3
"""
Test script to verify the backend returns OPEN_CLASSROOM JSON for course requests
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BASE_URL}/api/v1/ai/chat"

def test_course_request():
    """Test that 'Create a course on Python' returns JSON"""
    
    print("🧪 Testing course creation request...")
    print("=" * 60)
    
    payload = {
        "message": "Create a course on Python programming",
        "conversationHistory": [],
        "context": None
    }
    
    print(f"📤 Sending: {payload['message']}")
    
    try:
        response = requests.post(CHAT_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        response_text = data.get("response", "")
        
        print(f"\n📥 Response ({len(response_text)} chars):")
        print("-" * 60)
        print(response_text[:500] + ("..." if len(response_text) > 500 else ""))
        print("-" * 60)
        
        # Check if it contains OPEN_CLASSROOM
        if "OPEN_CLASSROOM" in response_text:
            print("\n✅ SUCCESS: Response contains OPEN_CLASSROOM JSON!")
            
            # Try to extract and validate JSON
            if response_text.strip().startswith("{"):
                try:
                    parsed = json.loads(response_text)
                    if parsed.get("type") == "OPEN_CLASSROOM":
                        print("✅ JSON is valid and properly structured!")
                        print(f"   Course Title: {parsed.get('payload', {}).get('course', {}).get('title')}")
                        print(f"   Topic: {parsed.get('payload', {}).get('course', {}).get('title')}")
                        return True
                except json.JSONDecodeError as e:
                    print(f"⚠️  JSON parsing failed: {e}")
            else:
                print("⚠️  Response contains OPEN_CLASSROOM but isn't pure JSON")
                print("    (The iOS parser should still extract it)")
        else:
            print("\n❌ FAIL: Response does NOT contain OPEN_CLASSROOM")
            print("    The AI returned plain text instead of the JSON command")
            
        return False
        
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to backend")
        print("   Make sure the server is running: python3 start_server.py")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_normal_question():
    """Test that 'What is a variable?' returns normal text (no JSON)"""
    
    print("\n\n🧪 Testing normal question (should NOT return JSON)...")
    print("=" * 60)
    
    payload = {
        "message": "What is a variable in Python?",
        "conversationHistory": [],
        "context": None
    }
    
    print(f"📤 Sending: {payload['message']}")
    
    try:
        response = requests.post(CHAT_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        response_text = data.get("response", "")
        
        print(f"\n📥 Response ({len(response_text)} chars):")
        print("-" * 60)
        print(response_text[:300] + ("..." if len(response_text) > 300 else ""))
        print("-" * 60)
        
        # Should NOT contain OPEN_CLASSROOM
        if "OPEN_CLASSROOM" not in response_text:
            print("\n✅ SUCCESS: Normal question returned plain text (correct!)")
            return True
        else:
            print("\n⚠️  WARNING: Normal question returned OPEN_CLASSROOM JSON")
            print("    The AI should only return JSON for course requests")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Lyo Backend Chat JSON Commands")
    print("=" * 60)
    print("Waiting for backend to start...")
    time.sleep(3)
    
    result1 = test_course_request()
    result2 = test_normal_question()
    
    print("\n\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Course Request Test: {'✅ PASS' if result1 else '❌ FAIL'}")
    print(f"Normal Question Test: {'✅ PASS' if result2 else '❌ FAIL'}")
    
    if result1 and result2:
        print("\n🎉 All tests passed! The backend is configured correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
