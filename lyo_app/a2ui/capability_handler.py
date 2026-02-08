import json
import logging
from typing import List, Dict, Any, Optional, Set
from fastapi import Header
from datetime import datetime

logger = logging.getLogger(__name__)


# ==============================================================================
# MARK: - Client Capabilities
# ==============================================================================

class ClientCapabilities:
    """Wrapper for client capabilities sent via headers"""
    
    # Basic types that legacy clients always support
    BASIC_TYPES = {"text", "button", "vstack", "hstack", "image", "spacer", "divider"}
    
    def __init__(self, header_value: Optional[str] = None, version_header: Optional[str] = None):
        self.version = "1.0.0"
        self.build = "1"
        self.supported_components: Set[str] = set()
        self.features: Dict[str, bool] = {}
        self.platform = "unknown"
        
        # Parse version header (format: "1.0.0+123")
        if version_header:
            self._parse_version(version_header)
        
        # Parse capabilities header (semicolon-separated or JSON)
        if header_value:
            self._parse_header(header_value)
            
    def _parse_version(self, version_header: str):
        """Parse X-Client-Version header (format: 1.0.0+123)"""
        try:
            if "+" in version_header:
                self.version, self.build = version_header.split("+", 1)
            else:
                self.version = version_header
        except Exception as e:
            logger.warning(f"Failed to parse version header: {e}")
            
    def _parse_header(self, header_value: str):
        """Parse X-Client-Capabilities header"""
        try:
            # Try JSON format first
            if header_value.strip().startswith("{"):
                data = json.loads(header_value)
                self.version = data.get("version", self.version)
                self.supported_components = set(data.get("components", []))
                self.features = data.get("features", {})
                self.platform = data.get("platform", "unknown")
            else:
                # Fallback to semicolon-separated format (compact header)
                self.supported_components = set(
                    c.strip().lower() for c in header_value.split(";") if c.strip()
                )
            
            logger.debug(f"Parsed client capabilities: {len(self.supported_components)} components")
        except json.JSONDecodeError:
            # Try semicolon-separated as fallback
            self.supported_components = set(
                c.strip().lower() for c in header_value.split(";") if c.strip()
            )
        except Exception as e:
            logger.error(f"Error processing capabilities: {e}")

    def supports(self, component_type: str) -> bool:
        """Check if client supports a specific component type"""
        component_lower = component_type.lower()
        
        # If no components specified, assume legacy client (basic types only)
        if not self.supported_components:
            return component_lower in self.BASIC_TYPES
            
        return component_lower in self.supported_components
    
    def has_feature(self, feature: str) -> bool:
        """Check if client has a specific feature enabled"""
        return self.features.get(feature, False)


# ==============================================================================
# MARK: - Protocol Adapter (Component Filtering)
# ==============================================================================

class LyoProtocolAdapter:
    """
    Filters AI-generated A2UI components based on client capabilities.
    
    Part of the Unbreakable Protocol - ensures iOS never receives
    components it can't render. Creates graceful fallbacks instead.
    """
    
    def __init__(self, capabilities: ClientCapabilities):
        self.capabilities = capabilities
        self.fallback_count = 0
        self.fallback_types: List[str] = []
    
    def adapt(self, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter a list of A2UI components, replacing unsupported ones with fallbacks.
        
        Args:
            components: List of A2UI component dictionaries
            
        Returns:
            Filtered list with unsupported components replaced
        """
        adapted = []
        
        for component in components:
            adapted_component = self._adapt_component(component)
            if adapted_component:
                adapted.append(adapted_component)
        
        # Log telemetry if any fallbacks occurred
        if self.fallback_count > 0:
            self._log_fallback_telemetry()
        
        return adapted
    
    def _adapt_component(self, component: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Adapt a single component, including children recursively."""
        if not isinstance(component, dict):
            return None
        
        component_type = component.get("type", "unknown")
        
        # Check if supported
        if self.capabilities.supports(component_type):
            # Component is supported - recursively process children
            adapted = component.copy()
            
            if "children" in adapted and isinstance(adapted["children"], list):
                adapted["children"] = [
                    self._adapt_component(child) 
                    for child in adapted["children"]
                    if self._adapt_component(child) is not None
                ]
            
            return adapted
        else:
            # Create fallback
            return self._create_fallback(component)
    
    def _create_fallback(self, original: Dict[str, Any]) -> Dict[str, Any]:
        """Create a text fallback for an unsupported component."""
        component_type = original.get("type", "unknown")
        props = original.get("props", {})
        
        # Track for telemetry
        self.fallback_count += 1
        self.fallback_types.append(component_type)
        
        # Try to extract meaningful text from the original
        fallback_text = (
            props.get("fallback_text") or 
            props.get("text") or 
            props.get("title") or 
            props.get("label") or
            f"[{component_type}]"
        )
        
        # Create fallback component
        return {
            "type": "fallback",
            "id": original.get("id", f"fallback-{self.fallback_count}"),
            "props": {
                "original_type": component_type,
                "fallback_text": fallback_text,
                "web_url": props.get("web_url"),
                "message": f"'{component_type}' requires app update"
            }
        }
    
    def _log_fallback_telemetry(self):
        """Log telemetry about fallback events for analytics."""
        logger.info(
            f"[Capability Fallback] Client v{self.capabilities.version} "
            f"({self.capabilities.platform}): {self.fallback_count} components replaced. "
            f"Types: {', '.join(set(self.fallback_types))}"
        )
        
        # In production, this would send to an analytics service
        # analytics.track("capability_fallback", {
        #     "client_version": self.capabilities.version,
        #     "platform": self.capabilities.platform,
        #     "fallback_count": self.fallback_count,
        #     "fallback_types": list(set(self.fallback_types)),
        #     "timestamp": datetime.utcnow().isoformat()
        # })


# ==============================================================================
# MARK: - FastAPI Dependencies
# ==============================================================================

def get_client_capabilities(
    x_client_capabilities: Optional[str] = Header(None),
    x_client_version: Optional[str] = Header(None)
) -> ClientCapabilities:
    """FastAPI dependency to extract capabilities from request headers."""
    return ClientCapabilities(
        header_value=x_client_capabilities,
        version_header=x_client_version
    )


def get_protocol_adapter(
    capabilities: ClientCapabilities = None
) -> LyoProtocolAdapter:
    """FastAPI dependency to get a protocol adapter for filtering components."""
    if capabilities is None:
        capabilities = ClientCapabilities()
    return LyoProtocolAdapter(capabilities)


# ==============================================================================
# MARK: - Utility Functions
# ==============================================================================

def filter_components_for_client(
    components: List[Dict[str, Any]],
    capabilities: ClientCapabilities
) -> List[Dict[str, Any]]:
    """
    Convenience function to filter components for a client.
    
    Usage:
        filtered = filter_components_for_client(components, request_capabilities)
    """
    adapter = LyoProtocolAdapter(capabilities)
    return adapter.adapt(components)

