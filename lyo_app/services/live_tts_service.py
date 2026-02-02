import os
import asyncio
import logging
from typing import Optional, AsyncGenerator
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class LiveTTSService:
    """Service for real-time text-to-speech using OpenAI."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        self.voice = os.getenv("CHATGPT_TTS_VOICE", "nova")
        
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize text to raw PCM audio stream."""
        if not self.client:
            logger.warning("⚠️ OpenAI client not initialized. TTS disabled.")
            return

        try:
            # Note: response_format="pcm" returns raw 24kHz 16-bit mono PCM
            async with self.client.audio.speech.with_streaming_response.create(
                model="tts-1",
                voice=self.voice,
                input=text,
                response_format="pcm"
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=4096):
                    yield chunk
                    
        except Exception as e:
            logger.error(f"❌ TTS Synthesis error: {e}")

    async def synthesize_all(self, text: str) -> bytes:
        """Synthesize entire text and return bytes."""
        audio_data = b""
        async for chunk in self.synthesize_stream(text):
            audio_data += chunk
        return audio_data
