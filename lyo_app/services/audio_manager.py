
"""
Audio WebSocket Manager for True Live Mode.
Handles bidirectional audio streaming (PCM 16-bit 24kHz) between iOS and Backend.
"""

import asyncio
import logging
import random
from typing import Dict, Optional, Set, List
from fastapi import WebSocket, WebSocketDisconnect
import numpy as np
try:
    import webrtcvad
except ImportError:
    webrtcvad = None
    
import json
from lyo_app.services.live_stt_service import DeepgramSTTService
from lyo_app.services.live_tts_service import LiveTTSService
from lyo_app.core.ai_resilience import ai_resilience_manager
from sqlalchemy import select
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.classroom.models import ClassroomSession
from lyo_app.feeds.addictive_algorithm import addictive_feed_algorithm
from lyo_app.services.highlight_service import highlight_service

logger = logging.getLogger(__name__)

class AudioWebSocketManager:
    def __init__(self):
        # Active audio sessions: session_id -> ActiveAudioSession
        self.active_sessions: Dict[str, 'ActiveAudioSession'] = {}
        
        # Audio configuration
        self.SAMPLE_RATE = 24000
        self.CHANNELS = 1
        self.DTYPE = np.int16
        self.VAD_FRAME_MS = 20
        self.VAD_SAMPLES_PER_FRAME = int(self.SAMPLE_RATE * (self.VAD_FRAME_MS / 1000))
        
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept connection and register session."""
        await websocket.accept()
        session = ActiveAudioSession(session_id, websocket, self)
        self.active_sessions[session_id] = session
        await session.start()
        logger.info(f"Audio session connected/started: {session_id}")
        
    def disconnect(self, session_id: str):
        """Remove session."""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            # Since disconnect is synchronous, we use a task
            asyncio.create_task(session.stop())
            del self.active_sessions[session_id]
            logger.info(f"Audio session stopped/disconnected: {session_id}")
            
    async def process_audio_stream(self, websocket: WebSocket, session_id: str):
        """
        Main loop for processing incoming audio packets.
        Expected format: Raw PCM bytes.
        """
        try:
            while True:
                # Receive raw bytes
                data = await websocket.receive_bytes()
                
                if session_id in self.active_sessions:
                    await self.active_sessions[session_id].handle_audio(data)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {session_id}")
            self.disconnect(session_id)
        except Exception as e:
            logger.error(f"Error in audio stream {session_id}: {e}")
            self.disconnect(session_id)
            
class ActiveAudioSession:
    def __init__(self, session_id: str, websocket: WebSocket, manager: AudioWebSocketManager):
        self.session_id = session_id
        self.websocket = websocket
        self.manager = manager
        
        # Services
        self.stt_service = DeepgramSTTService()
        self.tts_service = LiveTTSService()
        
        # VAD
        self.vad = webrtcvad.Vad(3) if webrtcvad else None
        
        # Session state
        self.buffer = bytearray()
        self.frame_size = manager.VAD_SAMPLES_PER_FRAME * 2
        self.is_speaking = False
        self.silence_frames = 0
        self.MAX_SILENCE_FRAMES = 15
        
        # AI Orchestration
        self.history = [{"role": "system", "content": "You are Lyo, a helpful AI tutor. Keep responses short and conversational for voice interaction."}]
        self.ai_task: Optional[asyncio.Task] = None
        self.is_ai_responding = False
        
        # Personalization State
        self.user_id: Optional[int] = None
        self.user_profile = None
    
    async def start(self):
        await self._setup_personalization()
        await self.stt_service.start_streaming(self.handle_transcript)
        
    async def _setup_personalization(self):
        """Fetch user profile and customize AI personality."""
        try:
            async with AsyncSessionLocal() as db:
                try:
                    session_id_int = int(self.session_id)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid session_id for DB lookup: {self.session_id}")
                    return

                result = await db.execute(select(ClassroomSession).where(ClassroomSession.id == session_id_int))
                session_obj = result.scalar_one_or_none()
                
                if session_obj:
                    self.user_id = session_obj.user_id
                    self.user_profile = await addictive_feed_algorithm._get_user_profile(self.user_id, db)
                    
                    # Inject personalized system prompt context
                    # Use psychological triggers from the addictive algorithm
                    personal_context = (
                        f"\n\nUSER PROFILE CONTEXT:\n"
                        f"- Attention Span: {self.user_profile.attention_span_seconds}s\n"
                        f"- Dopamine Pattern: {self.user_profile.dopamine_response_pattern}\n"
                        f"- Current Mood: {self.user_profile.emotional_state}\n"
                        f"- Binge Tendency: {self.user_profile.binge_watching_tendency}\n"
                        f"ADJUSTMENT: Use '{self.user_profile.dopamine_response_pattern}' communication style. "
                        f"Trigger their '{random.choice(self.user_profile.curiosity_triggers)}' curiosity."
                    )
                    self.history[0]["content"] += personal_context
                    logger.info(f"👤 Personalized session for user {self.user_id}")
                    
                    # Send hello widget
                    await self.push_widget("session_start", {
                        "user_name": session_obj.user.name if session_obj.user else "User",
                        "mood": self.user_profile.emotional_state
                    })
        except Exception as e:
            logger.error(f"Error setting up personalization: {e}")

    async def push_widget(self, component_type: str, data: dict):
        """Push a UI widget to the iOS client."""
        try:
            await self.websocket.send_text(json.dumps({
                "type": "widget",
                "component": component_type,
                "data": data
            }))
            logger.info(f"🎨 Pushed widget '{component_type}' to session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to push widget: {e}")
        
    async def stop(self):
        await self.stt_service.stop_streaming()
        if self.ai_task:
            self.ai_task.cancel()
        
        # Trigger Mastery Highlight generation in background for the feed
        if self.user_id and len(self.history) > 3:
            try:
                session_id_int = int(self.session_id)
                asyncio.create_task(highlight_service.generate_mastery_highlight(
                    self.user_id, self.history, session_id_int
                ))
            except Exception as e:
                logger.error(f"Error triggering highlight: {e}")
        
    async def handle_audio(self, data: bytes):
        """Process incoming audio bytes with VAD and STT."""
        self.buffer.extend(data)
        while len(self.buffer) >= self.frame_size:
            frame = self.buffer[:self.frame_size]
            del self.buffer[:self.frame_size]
            await self.stt_service.send_audio(frame)
            
            # Local VAD check for barge-in
            is_speech = self.check_speech(frame)
            self.update_vad_state(is_speech)

    def check_speech(self, frame: bytes) -> bool:
        if self.vad and self.manager.SAMPLE_RATE in [8000, 16000, 32000, 48000]:
            try:
                return self.vad.is_speech(frame, self.manager.SAMPLE_RATE)
            except:
                pass
        
        # Energy fallback
        audio_array = np.frombuffer(frame, dtype=np.int16)
        energy = np.sqrt(np.mean(audio_array.astype(np.float64)**2))
        return energy > 600

    def update_vad_state(self, is_speech: bool):
        if is_speech:
            if not self.is_speaking:
                self.is_speaking = True
                logger.info(f"🎙️ User speaking - Session {self.session_id}")
                if self.is_ai_responding:
                    self.interrupt_ai()
            self.silence_frames = 0
        else:
            if self.is_speaking:
                self.silence_frames += 1
                if self.silence_frames > self.MAX_SILENCE_FRAMES:
                    self.is_speaking = False
                    logger.info(f"🔇 User finished speaking - Session {self.session_id}")

    def interrupt_ai(self):
        """Stop current AI response for barge-in."""
        if self.ai_task and not self.ai_task.done():
            self.ai_task.cancel()
            logger.info(f"🛑 AI Interrupted in {self.session_id}")
            
        self.is_ai_responding = False
        # Notify client to stop playback
        asyncio.create_task(self.websocket.send_text(json.dumps({"type": "interrupt"})))

    def handle_transcript(self, text: str, is_final: bool):
        """Callback from STT."""
        if not text.strip(): return
        
        # Send transcript to client for UI
        asyncio.create_task(self.websocket.send_text(json.dumps({
            "type": "transcript",
            "text": text,
            "is_final": is_final
        })))

        if is_final:
            self.history.append({"role": "user", "content": text})
            # Start AI response task
            if self.ai_task: self.ai_task.cancel()
            self.ai_task = asyncio.create_task(self.process_ai_response())

    async def process_ai_response(self):
        """Stream LLM response and TTS it."""
        self.is_ai_responding = True
        try:
            full_response = ""
            sentence_buffer = ""
            
            # Stream tokens
            async for token in ai_resilience_manager.stream_chat_completion(self.history):
                full_response += token
                sentence_buffer += token
                
                # If we have a complete sentence, synthesize it
                if any(p in token for p in [".", "!", "?", "\n"]):
                    sentence = sentence_buffer.strip()
                    if len(sentence) > 5:
                        logger.info(f"Generating TTS for: {sentence}")
                        # Send transcript for AI to client
                        await self.websocket.send_text(json.dumps({
                            "type": "ai_transcript",
                            "text": sentence,
                            "is_final": False
                        }))
                        
                        # Stream TTS audio
                        async for audio_chunk in self.tts_service.synthesize_stream(sentence):
                            await self.websocket.send_bytes(audio_chunk)
                        
                        sentence_buffer = ""

            # Final bit of sentence if any
            if sentence_buffer.strip():
                async for audio_chunk in self.tts_service.synthesize_stream(sentence_buffer):
                    await self.websocket.send_bytes(audio_chunk)

            self.history.append({"role": "assistant", "content": full_response})
            logger.info(f"✅ AI Response complete: {full_response[:50]}...")
            
            # Check for widget triggers in full response
            # Format: [[WIDGET: type, data_json]]
            if "[[WIDGET:" in full_response:
                self._handle_widget_triggers(full_response)

            # Notify finished
            await self.websocket.send_text(json.dumps({"type": "ai_complete"}))

        except asyncio.CancelledError:
            logger.info("AI response task cancelled (interrupted)")
        except Exception as e:
            logger.error(f"Error processing AI response: {e}")
        finally:
            self.is_ai_responding = False

    def _handle_widget_triggers(self, text: str):
        """Extract and push widgets from AI text."""
        import re
        pattern = r"\[\[WIDGET:\s*(\w+),\s*({.*})\]\]"
        matches = re.finditer(pattern, text)
        for match in matches:
            widget_type = match.group(1)
            widget_data_str = match.group(2)
            try:
                widget_data = json.loads(widget_data_str)
                asyncio.create_task(self.push_widget(widget_type, widget_data))
            except Exception as e:
                logger.error(f"Error parsing widget JSON: {e}")

# Global instance
audio_manager = AudioWebSocketManager()
