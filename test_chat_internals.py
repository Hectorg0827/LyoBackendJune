import asyncio
import logging
import sys
import os

# Set up path
sys.path.append("/Users/hectorgarcia/Desktop/LyoBackendJune")

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.personalization.service import PersonalizationEngine
from lyo_app.core.database import get_db

logging.basicConfig(level=logging.INFO)

async def test_chat():
    print("--- Testing Chat Internals ---")
    
    # 1. Test AI Resilience
    print("1. Testing AI Resilience...")
    try:
        messages = [
            {"role": "system", "content": "You are Lyo."},
            {"role": "user", "content": "Hello!"}
        ]
        result = await ai_resilience_manager.chat_completion(messages)
        content = result.get("content") or result.get("response")
        print(f"✅ AI Response: {content[:50]}...")
    except Exception as e:
        print(f"❌ AI Resilience failed: {e}")
        return

    # 2. Test Personalization (if possible without real user)
    print("2. Testing PersonalizationEngine initialization...")
    try:
        engine = PersonalizationEngine()
        print("✅ PersonalizationEngine initialized")
    except Exception as e:
        print(f"❌ PersonalizationEngine failed: {e}")

    print("--- Test Complete ---")

if __name__ == "__main__":
    asyncio.run(test_chat())
