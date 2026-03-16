import uuid
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class LyoNexusFactory:
    """
    Factory responsible for taking raw strings and wrapping them 
    in strictly formatted Lyo v0.9 JSON Bricks.
    Enforces Adjacency List formatting (id, parent_id, order).
    """
    
    def __init__(self):
        # We could use Pydantic models here for strict validation, 
        # using Dicts for rapid prototyping in v0.9
        pass

    def create_text_brick(
        self, 
        text: str, 
        capabilities: List[str],
        parent_id: str,
        order: int
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a fundamental Text brick.
        """
        # Capability check
        if "lyo_v1" not in capabilities:
            # Fallback for completely unsupported clients?
            # In a strict bouncer model, maybe we drop or convert
            pass
            
        brick_id = f"text_{uuid.uuid4().hex[:8]}"
        
        return {
            "id": brick_id,
            "parent_id": parent_id,
            "type": "text",
            "order": order,
            "content": {"text": text}
        }

    def create_media_placeholder(
        self, 
        query: str, 
        capabilities: List[str],
        parent_id: str,
        order: int
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a loading placeholder for media elements requested via tags.
        """
        # Strict Bouncer check: does iOS support images?
        # Assuming true for v0.9 scope, but could check capabilities
        
        brick_id = f"img_{uuid.uuid4().hex[:8]}"
        
        return {
            "id": brick_id,
            "parent_id": parent_id,
            "type": "media",
            "variant": "image",
            "status": "loading",
            "order": order,
            "content": {"placeholder": query}, # Metadata for debugging
            "url": None
        }

    def create_update_brick(
        self,
        brick_id: str,
        update_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Creates a tiny JSON update object to hit the 'update_id' listener on iOS.
        """
        return {
            "update_id": brick_id,
            **update_payload
        }

    def create_emotion_brick(
        self,
        emotion: str,
        capabilities: List[str],
        parent_id: str,
        order: int
    ) -> Optional[Dict[str, Any]]:
        """
        Creates an Emotion brick to sync vocal and visual affect.
        """
        brick_id = f"emo_{uuid.uuid4().hex[:8]}"
        
        return {
            "id": brick_id,
            "parent_id": parent_id,
            "type": "emotion",
            "order": order,
            "content": {"text": emotion}
        }
