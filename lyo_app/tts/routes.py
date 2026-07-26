"""Authenticated REST routes for Lyo's shared classroom voice."""

import base64
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
import logging

from lyo_app.auth.dependencies import get_current_user_or_guest
from lyo_app.auth.schemas import UserRead

from .service import (
    get_tts_service,
    Voice,
    AudioFormat,
    Model,
    TTSUnavailableError,
    VOICE_PROFILES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["Text-to-Speech"])


# Request/Response Models
class SynthesizeRequest(BaseModel):
    """Request to synthesize speech"""
    text: str = Field(..., min_length=1, max_length=1200, description="One short teaching turn")
    voice: Optional[Voice] = Field(default=None, description="Voice to use")
    model: Optional[Model] = Field(default="tts-1-hd", description="TTS model")
    format: Optional[AudioFormat] = Field(default="mp3", description="Output format")
    speed: float = Field(default=0.98, ge=0.75, le=1.25, description="Classroom speech speed")
    content_type: Optional[str] = Field(default=None, description="Content type for auto voice selection")
    language: str = Field(
        default="auto",
        max_length=16,
        description="BCP-47 locale such as es-US, or auto for text detection",
    )
    
    
class SynthesizeResponse(BaseModel):
    """Response with synthesized audio"""
    audio_base64: str = Field(..., description="Base64 encoded audio")
    voice: str = Field(..., description="Voice used")
    format: str = Field(..., description="Audio format")
    duration_estimate_seconds: float = Field(..., description="Estimated duration")
    language_code: str = Field(..., description="Resolved spoken locale")
    provider: str = Field(..., description="Configured rendering provider")
    provider_voice: str = Field(..., description="Canonical provider voice")
    

class VoiceInfo(BaseModel):
    """Voice information"""
    voice: str
    id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: str
    best_for: List[str]
    personality: str
    

class VoicesResponse(BaseModel):
    """Available voices response"""
    voices: List[VoiceInfo]
    default_voice: str
    

class LessonAudioRequest(BaseModel):
    """Request to generate lesson audio"""
    lesson_content: dict = Field(..., description="Lesson content with blocks")
    voice: Optional[Voice] = Field(default=None, description="Override voice for all segments")
    format: Optional[AudioFormat] = Field(default="mp3", description="Output format")
    language: str = Field(default="auto", max_length=16)


class LessonAudioSegment(BaseModel):
    """Single lesson audio segment"""
    segment_id: str
    audio_base64: str
    duration_estimate_seconds: float
    voice: str


class LessonAudioResponse(BaseModel):
    """Full lesson audio response"""
    segments: List[LessonAudioSegment]
    total_duration_estimate_seconds: float


# Routes

@router.get("/health")
async def tts_health():
    """Check TTS service health"""
    try:
        service = await get_tts_service()
        provider_configured = service.provider_available
        return {
            "status": "healthy" if provider_configured else "degraded",
            "service": "tts",
            "voices_available": len(VOICE_PROFILES),
            "provider": service.config.provider,
            "provider_configured": provider_configured,
            "paid_fallback_enabled": bool(service.config.allow_openai_tts),
        }
    except Exception:
        return {
            "status": "degraded",
            "service": "tts",
            "provider_configured": False,
        }


@router.get("/voices", response_model=VoicesResponse)
async def list_voices(
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    List all available voices with their profiles
    
    Existing aliases remain stable for older clients. The server maps them to
    one canonical teacher identity for each spoken language.
    """
    service = await get_tts_service()
    voices = service.list_voices()
    
    return VoicesResponse(
        voices=[
            VoiceInfo(
                voice=v,
                id=v,
                name=v.title(),
                language="multilingual",
                description=info["description"],
                best_for=info["best_for"],
                personality=info["personality"]
            )
            for v, info in voices.items()
        ],
        default_voice=service.config.default_voice
    )


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(
    request: SynthesizeRequest,
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    Synthesize speech from text
    
    Returns base64-encoded audio for playback in iOS app.
    Automatically selects best voice if content_type is provided.
    """
    try:
        service = await get_tts_service()
        
        if not service.provider_available:
            raise HTTPException(
                status_code=503,
                detail="Shared classroom voice is not configured"
            )

        resolved = service.resolve_voice(
            request.text,
            voice=request.voice,
            language=request.language,
            content_type=request.content_type,
        )
        audio_data = await service.synthesize(
            text=request.text,
            voice=request.voice,
            model=request.model,
            format=request.format,
            speed=request.speed,
            content_type=request.content_type,
            language=request.language,
        )
        
        # Estimate duration (rough: ~150 words per minute at speed 1.0)
        word_count = len(request.text.split())
        duration_estimate = (word_count / 150) * 60 / request.speed
        
        return SynthesizeResponse(
            audio_base64=base64.b64encode(audio_data).decode(),
            voice=request.voice or service.config.default_voice,
            format=request.format or "mp3",
            duration_estimate_seconds=duration_estimate,
            language_code=resolved.language_code,
            provider=resolved.provider,
            provider_voice=resolved.provider_voice,
        )

    except TTSUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("TTS synthesis error: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Speech provider failed")


@router.post("/synthesize/stream")
async def synthesize_stream(
    request: SynthesizeRequest,
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    Stream synthesized speech
    
    Returns the shared cached audio response used by the Web classroom.
    Teaching turns are deliberately short, so rendering before the response
    also lets provider errors return a useful HTTP status instead of failing
    after streaming headers have already been sent.
    """
    try:
        service = await get_tts_service()
        audio_data = await service.synthesize(
            text=request.text,
            voice=request.voice,
            model=request.model,
            format=request.format or "mp3",
            speed=request.speed,
            content_type=request.content_type,
            language=request.language,
        )
                
        content_type = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm"
        }.get(request.format, "audio/mpeg")
        
        return Response(
            content=audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=speech.{request.format or 'mp3'}"
            }
        )
        
    except TTSUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("TTS streaming error: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Speech provider failed")


@router.post("/lesson/audio", response_model=LessonAudioResponse)
async def generate_lesson_audio(
    request: LessonAudioRequest,
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    Generate audio for an entire lesson
    
    Processes lesson content and generates audio for each segment:
    - Introduction
    - Content blocks (text explanations, code explanations)
    - Summary
    
    Automatically selects appropriate voice for each segment type.
    """
    try:
        service = await get_tts_service()
        
        audio_segments = await service.synthesize_lesson_audio(
            lesson_content=request.lesson_content,
            voice=request.voice,
            language=request.language,
        )
        
        segments = []
        total_duration = 0
        
        for segment_id, audio_data in audio_segments.items():
            # Rough duration estimate
            duration = len(audio_data) / 16000  # Rough MP3 estimate
            total_duration += duration
            
            segments.append(LessonAudioSegment(
                segment_id=segment_id,
                audio_base64=base64.b64encode(audio_data).decode(),
                duration_estimate_seconds=duration,
                voice=request.voice or service.config.default_voice
            ))
            
        return LessonAudioResponse(
            segments=segments,
            total_duration_estimate_seconds=total_duration
        )
        
    except Exception as e:
        logger.error(f"Lesson audio generation error: {e}")
        raise HTTPException(status_code=500, detail="Lesson audio generation failed")


@router.get("/synthesize/quick")
async def quick_synthesize(
    text: str = Query(..., min_length=1, max_length=1000, description="Text to speak"),
    voice: Optional[Voice] = Query(default="nova", description="Voice"),
    format: AudioFormat = Query(default="mp3", description="Format"),
    language: str = Query(default="auto", max_length=16),
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    Quick synthesis via GET request
    
    Simple endpoint for quick audio generation.
    Returns audio file directly.
    """
    try:
        service = await get_tts_service()
        
        audio_data = await service.synthesize(
            text=text,
            voice=voice,
            format=format,
            language=language,
        )
        
        content_type = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm"
        }.get(format, "audio/mpeg")
        
        return Response(
            content=audio_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=speech.{format}"
            }
        )
        
    except Exception as e:
        logger.error(f"Quick synthesis error: {e}")
        raise HTTPException(status_code=500, detail="Synthesis failed")


@router.get("/voice/{voice_id}")
async def get_voice_sample(
    voice_id: Voice,
    language: str = Query(default="en-US", max_length=16),
    _current_user: UserRead = Depends(get_current_user_or_guest),
):
    """
    Get voice sample/preview
    
    Returns a short audio sample demonstrating the voice.
    """
    try:
        service = await get_tts_service()
        
        # Sample text for each voice personality
        samples = {
            "alloy": "Hello! I'm Alloy, and I'll help explain concepts clearly and neutrally.",
            "echo": "Welcome, learner. I'm Echo, here to guide you through stories and history.",
            "fable": "Hello there! I'm Fable, and I'm absolutely thrilled to make learning exciting!",
            "onyx": "Greetings. I am Onyx, specializing in technical and scientific explanations.",
            "nova": "Hey! I'm Nova! Let's make learning fun and interactive together!",
            "shimmer": "Hello. I'm Shimmer, here to guide you through calm, reflective learning."
        }
        
        sample_text = samples.get(voice_id, f"Hello, I'm {voice_id}.")
        
        audio_data = await service.synthesize(
            text=sample_text,
            voice=voice_id,
            model="tts-1-hd",
            language=language,
        )
        
        voice_info = service.get_voice_info(voice_id)
        
        return {
            "voice": voice_id,
            "sample_text": sample_text,
            "audio_base64": base64.b64encode(audio_data).decode(),
            "description": voice_info.get("description", ""),
            "personality": voice_info.get("personality", "")
        }
        
    except Exception as e:
        logger.error(f"Voice sample error: {e}")
        raise HTTPException(status_code=500, detail="Voice sample generation failed")
