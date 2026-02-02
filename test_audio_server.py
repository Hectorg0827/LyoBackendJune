import logging

from fastapi import FastAPI, WebSocket
from lyo_app.services.audio_manager import audio_manager
from lyo_app.app_factory import create_app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use the full application factory to include all routers (chat, feed, etc.)
app = create_app()

# Ensure the V2 audio endpoint is also mounted (though it might be redundant if audio_router is included)
@app.websocket("/api/v2/chat/{session_id}/audio")
async def audio_endpoint(websocket: WebSocket, session_id: str):
    await audio_manager.connect(websocket, session_id)
    try:
        await audio_manager.process_audio_stream(websocket, session_id)
    finally:
        audio_manager.disconnect(session_id)

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to bind to all interfaces for LAN access
    uvicorn.run(app, host="0.0.0.0", port=8000)
