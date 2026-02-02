import asyncio
import os
import logging
from dotenv import load_dotenv

# Load .env file
load_dotenv()

from lyo_app.core.ai_resilience import ai_resilience_manager
from lyo_app.services.live_tts_service import LiveTTSService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_phase_3")

async def verify_llm_stream():
    logger.info("--- Testing LLM Stream ---")
    messages = [
        {"role": "system", "content": "You are Lyo."},
        {"role": "user", "content": "Hi Lyo, tell me a very short joke about AI."}
    ]
    
    full_text = ""
    print("AI Response: ", end="", flush=True)
    async for token in ai_resilience_manager.stream_chat_completion(messages):
        print(token, end="", flush=True)
        full_text += token
    print("\n")
    
    if len(full_text) > 5:
        logger.info("✅ LLM Stream successful")
        return full_text
    else:
        logger.error("❌ LLM Stream failed or returned empty")
        return None

async def verify_tts_synthesis(text: str):
    logger.info("--- Testing TTS Synthesis ---")
    tts_service = LiveTTSService()
    
    audio_bytes = b""
    chunk_count = 0
    async for chunk in tts_service.synthesize_stream(text):
        audio_bytes += chunk
        chunk_count += 1
        if chunk_count % 10 == 0:
            print(".", end="", flush=True)
    print("\n")
    
    if len(audio_bytes) > 1000:
        logger.info(f"✅ TTS Synthesis successful. Received {len(audio_bytes)} bytes in {chunk_count} chunks.")
        # Save to file for manual check if needed
        with open("test_tts_output.pcm", "wb") as f:
            f.write(audio_bytes)
        logger.info("Saved test_tts_output.pcm (24kHz 16-bit mono PCM)")
    else:
        logger.error("❌ TTS Synthesis failed or returned too little data")

async def main():
    # Make sure we have keys
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        logger.warning("No Gemini Key found in environment.")
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("No OpenAI Key found in environment.")
        
    await ai_resilience_manager.initialize()
    
    joke_text = await verify_llm_stream()
    if joke_text:
        await verify_tts_synthesis(joke_text)
        
    await ai_resilience_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
