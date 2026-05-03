#!/usr/bin/env python3
"""
Comprehensive test to verify AI chat returns REAL responses, not mocks
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    print("=" * 80)
    print("AI CHAT REAL RESPONSE VERIFICATION TEST")
    print("=" * 80)
    
    # Step 1: Load environment
    print("\n[1] Loading environment variables...")
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
            print(f"    ✅ Loaded .env from: {env_path.absolute()}")
        else:
            print(f"    ⚠️  .env not found at {env_path}")
    except ImportError:
        print("    ⚠️  python-dotenv not installed")
    
    # Step 2: Check API keys
    print("\n[2] Checking API key configuration...")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    print(f"    GEMINI_API_KEY: {f'[REDACTED, {len(gemini_key)} chars]' if gemini_key else '❌ NOT SET'}")
    print(f"    OPENAI_API_KEY: {f'[REDACTED, {len(openai_key)} chars]' if openai_key else '❌ NOT SET'}")
    
    if not gemini_key and not openai_key:
        print("\n❌ ERROR: No API keys found!")
        print("   Please ensure .env file has GEMINI_API_KEY or OPENAI_API_KEY set")
        return False
    
    # Step 3: Initialize AI Manager
    print("\n[3] Initializing AI Resilience Manager...")
    try:
        from lyo_app.core.ai_resilience import ai_resilience_manager
        await ai_resilience_manager.initialize()
        print("    ✅ AI Manager initialized")
        
        # Show which models are available
        models_info = []
        for model_name, model_cfg in ai_resilience_manager.models.items():
            has_key = bool(model_cfg.api_key)
            status = "✅" if has_key else "❌"
            models_info.append(f"       {status} {model_name}: {model_cfg.name}")
        print("    Available models:")
        for info in models_info:
            print(info)
    except Exception as e:
        print(f"    ❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 4: Test chat completion
    print("\n[4] Testing real AI chat completion...")
    test_messages = [
        {"role": "user", "content": "What is 2+2? Answer briefly."}
    ]
    
    try:
        print("    Sending request to AI providers...")
        response = await ai_resilience_manager.chat_completion(
            messages=test_messages,
            temperature=0.5,
            max_tokens=100,
        )
        
        content = response.get("content", "")
        model = response.get("model", "unknown")
        
        print(f"    Response received from: {model}")
        print(f"    Response: {content[:200]}")
        
        # Check if it's a real response or a mock/fallback
        mock_indicators = [
            "I'm having trouble responding",
            "Please try again",
            "All providers failed",
            "No AI models available",
            "fallback response",
        ]
        
        is_mock = any(indicator.lower() in content.lower() for indicator in mock_indicators)
        
        if is_mock:
            print("\n    ⚠️  WARNING: Response looks like a FALLBACK/MOCK")
            print("    This means all AI providers failed.")
            return False
        else:
            print("\n    ✅ SUCCESS: Received a REAL AI response!")
            return True
            
    except Exception as e:
        print(f"    ❌ Error during chat: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"Working directory: {os.getcwd()}\n")
    
    success = asyncio.run(main())
    
    print("\n" + "=" * 80)
    if success:
        print("✅ AI SYSTEM IS WORKING CORRECTLY - REAL RESPONSES ENABLED")
        print("\nNext steps:")
        print("1. Restart your backend: python -m uvicorn lyo_app.enhanced_main:app --reload")
        print("2. Test the chat endpoint: POST /api/v1/ai/chat")
        print("3. AI should now return real responses from Gemini or OpenAI")
    else:
        print("❌ AI SYSTEM HAS ISSUES - MOCK RESPONSES WILL BE USED")
        print("\nDebug steps:")
        print("1. Check that .env file exists in /Users/hectorgarcia/Desktop/LyoBackendJune/")
        print("2. Verify GEMINI_API_KEY or OPENAI_API_KEY are set in .env")
        print("3. Run this test again to see detailed error messages")
        print("4. Check backend logs for API call errors")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
