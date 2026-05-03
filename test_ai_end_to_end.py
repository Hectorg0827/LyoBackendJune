#!/usr/bin/env python3
"""
End-to-End AI System Test
Verifies that real AI responses are generated (not mock/fallback)
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Ensure we're in the right directory for .env loading
os.chdir(Path(__file__).parent)

# Load environment
from dotenv import load_dotenv
load_dotenv(override=False)

print("=" * 80)
print("END-TO-END AI SYSTEM TEST")
print("=" * 80)

# Test 1: Verify environment
print("\n1️⃣  ENVIRONMENT CHECK")
print("-" * 80)

gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

print(f"GEMINI_API_KEY loaded: {bool(gemini_key)}")
print(f"  Value preview: {gemini_key[:20]}..." if gemini_key else "")
print(f"OPENAI_API_KEY loaded: {bool(openai_key)}")
print(f"  Value preview: {openai_key[:20]}..." if openai_key else "")

if not gemini_key and not openai_key:
    print("\n❌ ERROR: No API keys found in environment!")
    print("Make sure you're running from the LyoBackendJune directory with .env file present.")
    sys.exit(1)

# Test 2: Import and initialize AI resilience manager
print("\n2️⃣  AI RESILIENCE MANAGER INITIALIZATION")
print("-" * 80)

try:
    from lyo_app.core.ai_resilience import AIResilienceManager
    print("✅ AIResilienceManager imported successfully")
except Exception as e:
    print(f"❌ Failed to import AIResilienceManager: {e}")
    sys.exit(1)

async def run_ai_test():
    """Run the actual AI test"""
    
    # Initialize manager
    manager = AIResilienceManager()
    
    try:
        await manager.initialize()
        print("✅ AIResilienceManager initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return False
    
    # Test 3: Check model configuration
    print("\n3️⃣  MODEL CONFIGURATION CHECK")
    print("-" * 80)
    
    print(f"Configured models: {list(manager.models.keys())}")
    for model_name, model_config in manager.models.items():
        has_key = bool(model_config.api_key)
        endpoint_display = "OpenAI API" if model_config.endpoint == "openai" else model_config.endpoint[:50]
        print(f"  • {model_name}")
        print(f"    - API Key: {'✅ Present' if has_key else '❌ Missing'}")
        print(f"    - Endpoint: {endpoint_display}")
        print(f"    - Priority: {model_config.priority}")
    
    # Test 4: Make an actual API call
    print("\n4️⃣  ACTUAL API CALL TEST")
    print("-" * 80)
    
    test_message = "What is 2+2?"
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": test_message}
    ]
    
    print(f"Test prompt: '{test_message}'")
    print("Calling chat_completion()...")
    
    try:
        result = await manager.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=100,
        )
        
        print(f"\n✅ API CALL SUCCEEDED")
        print(f"Response model: {result.get('model', 'Unknown')}")
        print(f"Response content: {result.get('content', 'No content')[:200]}")
        
        # Check if it's a real response or a fallback
        content = result.get('content', '').lower()
        fallback_indicators = [
            "having trouble",
            "try again",
            "stock",
            "mock",
            "fallback",
            "generic",
        ]
        
        is_fallback = any(indicator in content for indicator in fallback_indicators)
        
        if is_fallback:
            print(f"\n⚠️  WARNING: Response looks like a fallback/mock response")
            print(f"This suggests the API call failed and fell back to a generic message.")
            return False
        else:
            print(f"\n✅ Response looks like a REAL AI response (not fallback)")
            return True
            
    except Exception as e:
        print(f"\n❌ API CALL FAILED")
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        try:
            await manager.session.close() if manager.session else None
        except:
            pass

# Run the async test
print("\n" + "=" * 80)
success = asyncio.run(run_ai_test())
print("=" * 80)

if success:
    print("\n🎉 SUCCESS: AI system is returning REAL responses!")
    print("Your AI chat should now work properly in the app.")
    sys.exit(0)
else:
    print("\n❌ FAILURE: AI system is still returning fallback/mock responses")
    print("\nDEBUG STEPS:")
    print("1. Check the logs above for which provider failed and why")
    print("2. Verify API keys are correct in .env")
    print("3. Check internet connectivity to Google and OpenAI APIs")
    print("4. Try manually testing API keys with curl:")
    print("   - Gemini: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=YOUR_KEY")
    print("   - OpenAI: https://api.openai.com/v1/models (with Authorization header)")
    sys.exit(1)
