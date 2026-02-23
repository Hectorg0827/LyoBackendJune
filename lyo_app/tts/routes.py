"""
TTS Routes - REST API for Text-to-Speech
Premium audio experience for Lyo's AI Classroom
"""

import asyncio
import json
import base64
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
import logging

from .service import TTSService, get_tts_service, Voice, AudioFormat, Model, VOICE_PROFILES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["Text-to-Speech"])


# Request/Response Models
class SynthesizeRequest(BaseModel):
    """Request to synthesize speech"""
    text: str = Field(..., min_length=1, max_length=4096, description="Text to synthesize")
    voice: Optional[Voice] = Field(default=None, description="Voice to use")
    model: Optional[Model] = Field(default="tts-1-hd", description="TTS model")
    format: Optional[AudioFormat] = Field(default="mp3", description="Output format")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speech speed")
    content_type: Optional[str] = Field(default=None, description="Content type for auto voice selection")
    
    
class SynthesizeResponse(BaseModel):
    """Response with synthesized audio"""
    audio_base64: str = Field(..., description="Base64 encoded audio")
    voice: str = Field(..., description="Voice used")
    format: str = Field(..., description="Audio format")
    duration_estimate_seconds: float = Field(..., description="Estimated duration")
    

class VoiceInfo(BaseModel):
    """Voice information"""
    voice: str
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
        return {
            "status": "healthy",
            "service": "tts",
            "voices_available": len(VOICE_PROFILES),
            "api_configured": bool(service.config.api_key)
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "tts",
            "error": str(e)
        }


@router.get("/voices", response_model=VoicesResponse)
async def list_voices():
    """
    List all available voices with their profiles
    
    Returns 6 premium OpenAI voices optimized for education:
    - alloy: Neutral - general explanations
    - echo: Deep - storytelling
    - fable: British - engaging content
    - onyx: Authoritative - technical topics
    - nova: Energetic - interactive lessons
    - shimmer: Soft - calm study sessions
    """
    service = await get_tts_service()
    voices = service.list_voices()
    
    return VoicesResponse(
        voices=[
            VoiceInfo(
                voice=v,
                description=info["description"],
                best_for=info["best_for"],
                personality=info["personality"]
            )
            for v, info in voices.items()
        ],
        default_voice=service.config.default_voice
    )


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_speech(request: SynthesizeRequest):
    """
    Synthesize speech from text
    
    Returns base64-encoded audio for playback in iOS app.
    Automatically selects best voice if content_type is provided.
    """
    try:
        service = await get_tts_service()
        
        audio_data = await service.synthesize(
            text=request.text,
            voice=request.voice,
            model=request.model,
            format=request.format,
            speed=request.speed,
            content_type=request.content_type
        )
        
        # Estimate duration (rough: ~150 words per minute at speed 1.0)
        word_count = len(request.text.split())
        duration_estimate = (word_count / 150) * 60 / request.speed
        
        return SynthesizeResponse(
            audio_base64=base64.b64encode(audio_data).decode(),
            voice=request.voice or service.config.default_voice,
            format=request.format or "mp3",
            duration_estimate_seconds=duration_estimate
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"TTS synthesis error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {type(e).__name__}")


@router.post("/synthesize/stream")
async def synthesize_stream(request: SynthesizeRequest):
    """
    Stream synthesized speech
    
    Returns audio as streaming response for real-time playback.
    Ideal for long content or immediate playback start.
    """
    try:
        service = await get_tts_service()
        
        async def audio_stream():
            async for chunk in service.synthesize_streaming(
                text=request.text,
                voice=request.voice,
                model=request.model,
                format=request.format or "mp3",
                speed=request.speed
            ):
                yield chunk
                
        content_type = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm"
        }.get(request.format, "audio/mpeg")
        
        return StreamingResponse(
            audio_stream(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=speech.{request.format or 'mp3'}"
            }
        )
        
    except Exception as e:
        logger.error(f"TTS streaming error: {e}")
        raise HTTPException(status_code=500, detail="Speech streaming failed")


@router.post("/lesson/audio", response_model=LessonAudioResponse)
async def generate_lesson_audio(request: LessonAudioRequest):
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
            voice=request.voice
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
    format: AudioFormat = Query(default="mp3", description="Format")
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
            format=format
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
async def get_voice_sample(voice_id: Voice):
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
            model="tts-1-hd"
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
