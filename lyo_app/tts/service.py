"""
TTS Service - OpenAI Text-to-Speech Integration
Premium voices for Lyo's AI Classroom experience.

Voices:
- alloy: Neutral and balanced - great for general explanations
- echo: Deep and warm - perfect for storytelling and narratives
- fable: Expressive British accent - ideal for engaging content
- onyx: Deep and authoritative - excellent for serious topics
- nova: Youthful and energetic - great for interactive lessons
- shimmer: Soft and gentle - perfect for calming study sessions
"""

import asyncio
import hashlib
import aiohttp
import os
import logging
from typing import Optional, Literal, AsyncGenerator, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json

try:
    from lyo_app.integrations.gcp_secrets import get_secret
except Exception:
    def get_secret(name: str, default=None):
        return os.getenv(name, default)

logger = logging.getLogger(__name__)

# Voice personalities for the AI classroom
VOICE_PROFILES = {
    "alloy": {
        "description": "Neutral and balanced",
        "best_for": ["general_explanations", "definitions", "summaries"],
        "personality": "helpful_tutor"
    },
    "echo": {
        "description": "Deep and warm",
        "best_for": ["storytelling", "history", "narratives"],
        "personality": "wise_mentor"
    },
    "fable": {
        "description": "Expressive British accent",
        "best_for": ["engaging_content", "literature", "creative"],
        "personality": "enthusiastic_teacher"
    },
    "onyx": {
        "description": "Deep and authoritative",
        "best_for": ["science", "math", "technical"],
        "personality": "expert_professor"
    },
    "nova": {
        "description": "Youthful and energetic",
        "best_for": ["interactive_lessons", "quizzes", "encouragement"],
        "personality": "friendly_coach"
    },
    "shimmer": {
        "description": "Soft and gentle",
        "best_for": ["meditation", "study_music", "relaxation"],
        "personality": "calm_guide"
    }
}

Voice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
AudioFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
Model = Literal["tts-1", "tts-1-hd"]


@dataclass
class TTSConfig:
    """TTS Service Configuration"""
    api_key: str = ""
    default_voice: Voice = "nova"
    default_model: Model = "tts-1-hd"  # HD for classroom quality
    default_format: AudioFormat = "mp3"
    default_speed: float = 1.0
    cache_enabled: bool = True
    cache_dir: str = "/tmp/lyo_tts_cache"
    cache_ttl_hours: int = 24
    max_text_length: int = 4096


@dataclass
class CachedAudio:
    """Cached audio entry"""
    file_path: str
    created_at: datetime
    voice: str
    text_hash: str
    format: str
    size_bytes: int


class TTSService:
    """
    Premium Text-to-Speech Service for Lyo's AI Classroom
    
    Features:
    - 6 premium OpenAI voices optimized for education
    - HD audio quality for clear learning
    - Intelligent caching for fast responses
    - Streaming support for real-time lessons
    - Voice selection based on content type
    """
    
    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, CachedAudio] = {}
        self._initialized = False
        
    async def initialize(self):
        """Initialize TTS service with API key from secrets"""
        if self._initialized:
            return
            
        # Get OpenAI API key from secrets (strip to remove trailing newlines from Secret Manager)
        api_key = (get_secret("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")) or "").strip()
        if not api_key:
            logger.warning("OpenAI API key not found - TTS will use fallback")
        else:
            self.config.api_key = api_key
            
        # Create cache directory
        cache_path = Path(self.config.cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize HTTP session
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=60)
        )
        
        self._initialized = True
        logger.info(f"TTS Service initialized with {len(VOICE_PROFILES)} premium voices")
        
    async def close(self):
        """Cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None
        self._initialized = False
            
    def select_voice_for_content(self, content_type: str, topic: Optional[str] = None) -> Voice:
        """
        Intelligently select the best voice for content type
        
        Args:
            content_type: Type of content (explanation, story, quiz, etc.)
            topic: Optional topic for further refinement
            
        Returns:
            Best matching voice
        """
        content_voice_map = {
            # Educational content types
            "explanation": "alloy",
            "definition": "alloy",
            "summary": "alloy",
            
            # Narrative content
            "story": "echo",
            "history": "echo",
            "biography": "echo",
            
            # Engaging content
            "introduction": "fable",
            "welcome": "fable",
            "creative": "fable",
            
            # Technical content
            "science": "onyx",
            "math": "onyx",
            "technical": "onyx",
            "code": "onyx",
            
            # Interactive content
            "quiz": "nova",
            "exercise": "nova",
            "encouragement": "nova",
            "congratulations": "nova",
            
            # Calm content
            "meditation": "shimmer",
            "reflection": "shimmer",
            "study_tips": "shimmer"
        }
        
        return content_voice_map.get(content_type, self.config.default_voice)
        
    def _get_cache_key(self, text: str, voice: Voice, model: Model, speed: float) -> str:
        """Generate cache key for audio"""
        content = f"{text}:{voice}:{model}:{speed}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
        
    def _get_cached_audio(self, cache_key: str) -> Optional[bytes]:
        """Get audio from cache if valid"""
        if not self.config.cache_enabled:
            return None
            
        cached = self._cache.get(cache_key)
        if not cached:
            return None
            
        # Check TTL
        if datetime.now() - cached.created_at > timedelta(hours=self.config.cache_ttl_hours):
            del self._cache[cache_key]
            if os.path.exists(cached.file_path):
                os.remove(cached.file_path)
            return None
            
        # Read from file
        try:
            with open(cached.file_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None
            
    def _cache_audio(self, cache_key: str, audio_data: bytes, voice: Voice, format: AudioFormat):
        """Cache audio data"""
        if not self.config.cache_enabled:
            return
            
        file_path = os.path.join(self.config.cache_dir, f"{cache_key}.{format}")
        try:
            with open(file_path, "wb") as f:
                f.write(audio_data)
                
            self._cache[cache_key] = CachedAudio(
                file_path=file_path,
                created_at=datetime.now(),
                voice=voice,
                text_hash=cache_key,
                format=format,
                size_bytes=len(audio_data)
            )
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
            
    async def synthesize(
        self,
        text: str,
        voice: Optional[Voice] = None,
        model: Optional[Model] = None,
        format: Optional[AudioFormat] = None,
        speed: float = 1.0,
        content_type: Optional[str] = None
    ) -> bytes:
        """
        Synthesize speech from text
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (optional, will auto-select if content_type provided)
            model: TTS model (tts-1 or tts-1-hd)
            format: Output format (mp3, opus, aac, flac, wav, pcm)
            speed: Speed of speech (0.25 to 4.0)
            content_type: Content type for auto voice selection
            
        Returns:
            Audio data as bytes
        """
        if not self._initialized:
            await self.initialize()
            
        if not self.config.api_key:
            raise ValueError("OpenAI API key not configured")
            
        # Auto-select voice if not specified
        if voice is None:
            if content_type:
                voice = self.select_voice_for_content(content_type)
            else:
                voice = self.config.default_voice
                
        model = model or self.config.default_model
        format = format or self.config.default_format
        
        # Validate text length
        if len(text) > self.config.max_text_length:
            logger.warning(f"Text truncated from {len(text)} to {self.config.max_text_length}")
            text = text[:self.config.max_text_length]
            
        # Check cache
        cache_key = self._get_cache_key(text, voice, model, speed)
        cached = self._get_cached_audio(cache_key)
        if cached:
            logger.debug(f"TTS cache hit: {cache_key}")
            return cached
            
        # Make API call
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": format,
            "speed": speed
        }
        
        async with self._session.post(
            "https://api.openai.com/v1/audio/speech",
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"TTS API error: {response.status} - {error_text}")
                
            audio_data = await response.read()
            
        # Cache result
        self._cache_audio(cache_key, audio_data, voice, format)
        
        logger.info(f"TTS generated: {len(audio_data)} bytes, voice={voice}, model={model}")
        return audio_data
        
    async def synthesize_streaming(
        self,
        text: str,
        voice: Optional[Voice] = None,
        model: Optional[Model] = None,
        format: AudioFormat = "mp3",
        speed: float = 1.0,
        chunk_size: int = 1024
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized speech
        
        Yields audio chunks for real-time playback
        """
        if not self._initialized:
            await self.initialize()
            
        if not self.config.api_key:
            raise ValueError("OpenAI API key not configured")
            
        voice = voice or self.config.default_voice
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": format,
            "speed": speed
        }
        
        async with self._session.post(
            "https://api.openai.com/v1/audio/speech",
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"TTS streaming error: {response.status} - {error_text}")
                
            async for chunk in response.content.iter_chunked(chunk_size):
                yield chunk
                
    async def synthesize_lesson_audio(
        self,
        lesson_content: Dict[str, Any],
        voice: Optional[Voice] = None
    ) -> Dict[str, bytes]:
        """
        Generate audio for an entire lesson
        
        Returns dict of section_id -> audio bytes
        """
        audio_segments = {}
        
        # Introduction
        if "introduction" in lesson_content:
            voice_for_intro = voice or self.select_voice_for_content("introduction")
            audio_segments["introduction"] = await self.synthesize(
                lesson_content["introduction"],
                voice=voice_for_intro,
                content_type="introduction"
            )
            
        # Content blocks
        for i, block in enumerate(lesson_content.get("content_blocks", [])):
            block_type = block.get("block_type", "text")
            
            if block_type == "text":
                content = block.get("content", "")
                voice_for_block = voice or self.select_voice_for_content("explanation")
                audio_segments[f"block_{i}"] = await self.synthesize(
                    content,
                    voice=voice_for_block,
                    content_type="explanation"
                )
            elif block_type == "code":
                # Read code explanation, not the code itself
                explanation = block.get("explanation", "")
                if explanation:
                    voice_for_code = voice or self.select_voice_for_content("code")
                    audio_segments[f"block_{i}_explanation"] = await self.synthesize(
                        explanation,
                        voice=voice_for_code,
                        content_type="code"
                    )
                    
        # Summary
        if "summary" in lesson_content:
            voice_for_summary = voice or self.select_voice_for_content("summary")
            audio_segments["summary"] = await self.synthesize(
                lesson_content["summary"],
                voice=voice_for_summary,
                content_type="summary"
            )
            
        return audio_segments
        
    def get_voice_info(self, voice: Voice) -> Dict[str, Any]:
        """Get information about a voice"""
        profile = VOICE_PROFILES.get(voice, {})
        return {
            "voice": voice,
            "description": profile.get("description", ""),
            "best_for": profile.get("best_for", []),
            "personality": profile.get("personality", "")
        }
        
    def list_voices(self) -> Dict[str, Dict[str, Any]]:
        """List all available voices with their profiles"""
        return {voice: self.get_voice_info(voice) for voice in VOICE_PROFILES.keys()}


# Singleton instance
_tts_service: Optional[TTSService] = None


async def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
        await _tts_service.initialize()
    return _tts_service
