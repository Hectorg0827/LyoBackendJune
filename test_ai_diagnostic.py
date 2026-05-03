#!/usr/bin/env python3
"""
Diagnostic script to test AI API keys and models
"""
import os
import asyncio
import sys
sys.path.insert(0, '/Users/hectorgarcia/Desktop/LyoBackendJune')

async def test_ai_setup():
    print("=" * 80)
    print("🔍 AI CONFIGURATION DIAGNOSTIC")
    print("=" * 80)
    
    # Check environment variables
    print("\n📋 Environment Variables:")
    env_vars = ['GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY']
    for var in env_vars:
        val = os.getenv(var, 'NOT SET')
        is_set = val != 'NOT SET'
        redacted = f"[REDACTED - {len(val)} chars]" if is_set else "NOT SET"
        print(f"  {var}: {redacted}")
    
    # Try to load settings
    print("\n⚙️  Loading settings...")
    try:
        from lyo_app.core.config import settings
        print(f"  ✅ Settings loaded")
        print(f"    - Gemini API Key (from settings): {'[SET]' if settings.gemini_api_key else '[NOT SET]'}")
        print(f"    - OpenAI API Key (from settings): {'[SET]' if settings.openai_api_key else '[NOT SET]'}")
    except Exception as e:
        print(f"  ❌ Failed to load settings: {e}")
        return
    
    # Try to initialize AI manager
    print("\n🤖 Initializing AI Resilience Manager...")
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager
        await ai_resilience_manager.initialize()
        print(f"  ✅ AI Manager initialized")
        print(f"    - Models configured: {len(ai_resilience_manager.models)}")
        for name, config in ai_resilience_manager.models.items():
            has_key = bool(config.api_key)
            print(f"      • {name}: {'✅ API Key Set' if has_key else '❌ NO API KEY'}")
    except Exception as e:
        print(f"  ❌ Failed to initialize AI manager: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Try a test chat
    print("\n💬 Testing chat completion...")
    try:
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello! The AI API is working correctly!'"}
        ]
        result = await ai_resilience_manager.chat_completion(
            messages=test_messages,
            max_tokens=50,
            temperature=0.5
        )
        print(f"  Response: {result['content']}")
        print(f"  Model used: {result.get('model', 'unknown')}")
        print(f"  Is fallback: {result.get('is_fallback', False)}")
        
        if result.get('is_fallback'):
            print(f"\n  ⚠️  WARNING: This is a FALLBACK response!")
            print(f"     Error: {result.get('error', 'unknown')}")
        else:
            print(f"\n  ✅ SUCCESS: Real AI response!")
    except Exception as e:
        print(f"  ❌ Chat test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(test_ai_setup())
