import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import Header

logger = logging.getLogger(__name__)

class ClientCapabilities:
    """Wrapper for client capabilities sent via headers"""
    def __init__(self, header_value: Optional[str] = None):
        self.version = "1.0.0"
        self.supported_components = set()
        self.features = {}
        
        if header_value:
            self._parse_header(header_value)
            
    def _parse_header(self, header_value: str):
        try:
            data = json.loads(header_value)
            self.version = data.get("version", "1.0.0")
            self.supported_components = set(data.get("supportedComponents", []))
            self.features = data.get("features", {})
            logger.info(f"Parsed client capabilities: {len(self.supported_components)} components supported")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse capabilities header: {header_value}")
        except Exception as e:
            logger.error(f"Error processing capabilities: {e}")

    def supports(self, component_type: str) -> bool:
        """Check if client supports a specific component type"""
        # If no components specified, assume legacy client (support basic types)
        if not self.supported_components:
            return component_type in ["text", "button", "vstack", "hstack", "image"]
            
        return component_type in self.supported_components

def get_client_capabilities(
    x_client_capabilities: Optional[str] = Header(None)
) -> ClientCapabilities:
    """FastAPI dependency to extract capabilities"""
    return ClientCapabilities(x_client_capabilities)
