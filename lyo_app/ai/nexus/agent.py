import asyncio
import logging
import re
from typing import AsyncGenerator, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class LyoNexusAgent:
    """
    Independent middleware agent for A2UI v0.9.
    Takes a raw text stream from the "Brain" (Primary LLM), semantics-slices it,
    and yields complete JSON components (Adjacency List Bricks).
    """
    
    def __init__(self, factory, media_worker):
        """
        :param factory: Converts text/tags into validated A2UI JSON dicts.
        :param media_worker: Asynchronous worker for handling <media_req: ...>
        """
        self.factory = factory
        self.media_worker = media_worker
        self._buffer = ""
        
        # Regex to detect semantic splits
        # 1. Double newlines (paragraphs)
        # 2. Markdown headers (sections)
        # 3. Media tags: <media_req: something>
        self._boundary_pattern = re.compile(
            r'(\n\n|^#+ |<media_req:[^>]+>)'
        )
        self._media_tag_pattern = re.compile(r'<media_req:\s*([^>]+)>')

    async def process_stream(
        self, 
        text_stream: AsyncGenerator[str, None], 
        capabilities: List[str]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Consumes raw LLM tokens, chunks them, and yields validated JSON bricks.
        """
        self._buffer = ""
        parent_id = "root"  # In a flat adjacency list, chunks attach to a parent
        chunk_index = 0
        
        async for token in text_stream:
            self._buffer += token
            
            # Non-blocking heuristic slice check
            while True:
                match = self._boundary_pattern.search(self._buffer)
                if not match:
                    break
                
                # We found a boundary! Cut the text BEFORE the boundary
                boundary_start = match.start()
                boundary_end = match.end()
                boundary_text = match.group(1)
                
                chunk_text = self._buffer[:boundary_start].strip()
                
                if chunk_text:
                    chunk_index += 1
                    brick = self.factory.create_text_brick(
                        text=chunk_text, 
                        capabilities=capabilities,
                        parent_id=parent_id,
                        order=chunk_index
                    )
                    if brick:
                        yield brick
                        
                # Handle the boundary itself if it's a media tag
                if boundary_text.startswith("<media_req:"):
                    tag_match = self._media_tag_pattern.search(boundary_text)
                    if tag_match:
                        media_query = tag_match.group(1).strip()
                        chunk_index += 1
                        
                        # 1. Yield placeholder immediately
                        placeholder_brick = self.factory.create_media_placeholder(
                            query=media_query,
                            capabilities=capabilities,
                            parent_id=parent_id,
                            order=chunk_index
                        )
                        if placeholder_brick:
                            yield placeholder_brick
                            
                            # 2. Dispatch background generation worker
                            update_id = placeholder_brick.get("id")
                            asyncio.create_task(
                                self.media_worker.dispatch_media_generation(
                                    query=media_query,
                                    brick_id=update_id,
                                    media_type="image" # Defaulting for now
                                )
                            )
                
                # Empty the processed portion from the tank
                self._buffer = self._buffer[boundary_end:]
                
        # Flush the remainder of the buffer
        final_chunk = self._buffer.strip()
        if final_chunk:
            chunk_index += 1
            brick = self.factory.create_text_brick(
                text=final_chunk, 
                capabilities=capabilities,
                parent_id=parent_id,
                order=chunk_index
            )
            if brick:
                yield brick
