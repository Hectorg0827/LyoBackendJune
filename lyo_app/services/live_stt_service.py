import asyncio
import logging
import os
from typing import Optional, Callable
try:
    from deepgram import AsyncDeepgramClient
except ImportError:
    AsyncDeepgramClient = None

logger = logging.getLogger(__name__)

class DeepgramSTTService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        self._demo_mode = False
        
        if not self.api_key or not AsyncDeepgramClient:
            if not self.api_key:
                logger.warning("⚠️ DEEPGRAM_API_KEY not found. Using DEMO mode.")
            else:
                logger.warning("⚠️ Deepgram package not installed. Using DEMO mode.")
            self._demo_mode = True
            self.client = None
        else:
            self.client = AsyncDeepgramClient(api_key=self.api_key)
            
        self.socket = None
        self._running = False
        self._on_transcript = None
        self._audio_buffer = b""
        self._buffer_threshold = 8000  # ~250ms of 16kHz mono 16-bit audio (faster triggering for demo)

    async def start_streaming(self, on_transcript: Callable[[str, bool], None]):
        """Starts a streaming connection to Deepgram."""
        self._on_transcript = on_transcript
        self._running = True
        
        if self._demo_mode:
            logger.info("🎭 STT Demo Mode: Will simulate transcripts")
            asyncio.create_task(self._run_demo_mode())
            return
            
        if not self.client: 
            return
        
        # Start the context manager in a background task to keep it alive
        asyncio.create_task(self._run_socket())
    
    async def _run_demo_mode(self):
        """Demo mode: wait for audio data, then simulate a transcript."""
        demo_responses = [
            "Hello, can you help me learn something new?",
            "What topic should we explore today?",
            "I want to understand machine learning better.",
            "Can you explain how neural networks work?",
        ]
        response_idx = 0
        
        while self._running:
            await asyncio.sleep(0.1)
            
            # Check if we have enough audio data to trigger a "transcript"
            if len(self._audio_buffer) >= self._buffer_threshold:
                # Simulate processing delay
                await asyncio.sleep(0.3)
                
                if self._on_transcript:
                    transcript = demo_responses[response_idx % len(demo_responses)]
                    logger.info(f"🎭 Demo transcript: '{transcript}'")
                    self._on_transcript(transcript, True)  # is_final=True
                    response_idx += 1
                
                # Reset buffer
                self._audio_buffer = b""

    async def _run_socket(self):
        try:
            # Note: We use the listen.v1.connect which returns a context manager
            async with self.client.listen.v1.connect(
                model="nova-2",
                punctuate=True,
                language="en-US",
                encoding="linear16",
                channels=1,
                sample_rate=24000,
                interim_results=True,
                utterance_end_ms="1000",
                vad_events=True,
            ) as socket:
                self.socket = socket
                logger.info("✅ Deepgram socket established")
                
                async for message in socket:
                    if not self._running: break
                    try:
                        # Extract transcript
                        if hasattr(message, "channel"):
                            transcript = message.channel.alternatives[0].transcript
                            if transcript and self._on_transcript:
                                self._on_transcript(transcript, message.is_final)
                    except Exception as e:
                        logger.error(f"Error processing DG message: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Deepgram loop error: {e}")
        finally:
            self.socket = None
            self._running = False

    async def send_audio(self, data: bytes):
        """Send audio chunk to Deepgram or buffer for demo mode."""
        # In demo mode, accumulate audio to trigger transcript
        if self._demo_mode:
            self._audio_buffer += data
            return
            
        if self.socket:
            try:
                # V5 uses send_media or similar? 
                # According to socket_client.py, it has send_media
                self.socket.send_media(data)
            except Exception as e:
                logger.error(f"❌ Error sending audio to Deepgram: {e}")

    async def stop_streaming(self):
        """Stop transcription."""
        self._running = False
        if self.socket:
            # Most DG sockets have a finalize or similar
            try:
                # self.socket.finish() # Depends on Fern implementation
                pass
            except:
                pass
        logger.info("🔌 Deepgram streaming requested to stop")
