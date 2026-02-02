
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from lyo_app.services.audio_manager import audio_manager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/chat/{session_id}/audio")
async def audio_stream_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for True Live Mode (Full Duplex Audio).
    
    Protocol:
    - Transport: Binary (PCM 16-bit 24kHz)
    - Client sends: Raw audio bytes
    - Server sends: Raw audio bytes (TTS response)
    """
    await audio_manager.connect(websocket, session_id)
    try:
        await audio_manager.process_audio_stream(websocket, session_id)
    except WebSocketDisconnect:
        audio_manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
        audio_manager.disconnect(session_id)
