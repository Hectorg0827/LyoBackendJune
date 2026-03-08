import logging
import asyncio
from typing import Callable, Awaitable, Dict, Any

logger = logging.getLogger(__name__)

class LyoNexusMediaWorker:
    """
    Handles asynchronous media generation dispatched by the Nexus Agent.
    When a <media_req: ...> tag is found, Nexus yields a loading brick
    and tells this worker to actually fetch/generate the content.
    """
    
    def __init__(self, dispatch_update_callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """
        :param dispatch_update_callback: An async func that pipes 'update_id' blocks 
                                         back into the main SSE/WebSocket stream.
        """
        self.dispatch_update_callback = dispatch_update_callback
        
    async def dispatch_media_generation(self, query: str, brick_id: str, media_type: str = "image"):
        """
        Mock generation for now.
        In reality, this calls Runware/DALL-E, saves to S3, and gets a URL.
        """
        logger.info(f"🎨 [NEXUS WORKER] Starting media generation for '{query}' (Target: {brick_id})")
        
        # Simulate network generation latency
        await asyncio.sleep(2.0)
        
        # Mock result
        mock_url = f"https://generated.images.com/{query.replace(' ', '_')}.jpg"
        
        logger.info(f"✅ [NEXUS WORKER] Completed media generation: {mock_url}")
        
        # Send the tiny update JSON brick back to the stream
        update_brick = {
            "update_id": brick_id,
            "url": mock_url,
            "status": "loaded"
        }
        
        await self.dispatch_update_callback(update_brick)
