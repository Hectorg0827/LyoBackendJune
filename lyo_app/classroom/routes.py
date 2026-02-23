from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Any
import logging
import json

from .generator import ContentGenerator
from .schemas import LyoStreamChunk

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/classroom",
    tags=["classroom"]
)

@router.websocket("/ws/lesson/{topic}")
async def websocket_lesson_stream(websocket: WebSocket, topic: str):
    """
    WebSocket endpoint for streaming a complete Lyo Classroom lesson
    composed of the 7 exact card types.
    """
    await websocket.accept()
    
    generator = ContentGenerator()
    
    try:
        # Stream the lesson chunks
        async for chunk in generator.stream_lesson(topic):
            # Send the Pydantic model as JSON
            data_to_send = chunk.model_dump(mode='json', exclude_none=True)
            await websocket.send_json(data_to_send)
            
            # Simple heartbeat/logging
            if chunk.card:
                logger.info(f"Streamed card of type {chunk.card.type}")
            elif chunk.is_complete:
                logger.info("Lesson stream completed successfully.")
                
    except WebSocketDisconnect:
        logger.info(f"Client disconnected during {topic} lesson stream")
    except Exception as e:
        logger.error(f"Error in lesson stream: {e}")
        error_chunk = LyoStreamChunk(is_complete=True, card=None, metadata=None)
        # Ideally add an error wrapper here, but for now just send complete to close
        try:
            await websocket.send_json({"error": str(e), "is_complete": True})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
