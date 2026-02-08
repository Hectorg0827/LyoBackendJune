"""
Tests for capability_handler.py - LyoProtocolAdapter and ClientCapabilities

Run with: pytest tests/test_a2ui_capability_handler.py -v
"""

import pytest
from lyo_app.a2ui.capability_handler import (
    ClientCapabilities,
    LyoProtocolAdapter,
    filter_components_for_client,
)


class TestClientCapabilities:
    """Tests for ClientCapabilities class"""
    
    def test_empty_capabilities_defaults_to_basic(self):
        """Legacy clients (no header) should only support basic types"""
        caps = ClientCapabilities()
        
        assert caps.supports("text") is True
        assert caps.supports("button") is True
        assert caps.supports("vstack") is True
        assert caps.supports("hologram_3d") is False
        
    def test_parse_semicolon_format(self):
        """Semicolon-separated header should parse correctly"""
        caps = ClientCapabilities(header_value="text;button;quiz_mcq;video_player")
        
        assert caps.supports("text") is True
        assert caps.supports("quiz_mcq") is True
        assert caps.supports("video_player") is True
        assert caps.supports("unknown_type") is False
        
    def test_parse_json_format(self):
        """JSON header should parse correctly"""
        json_header = '{"version": "2.0.0", "components": ["text", "markdown", "code_block"], "platform": "ios"}'
        caps = ClientCapabilities(header_value=json_header)
        
        assert caps.version == "2.0.0"
        assert caps.platform == "ios"
        assert caps.supports("markdown") is True
        assert caps.supports("code_block") is True
        assert caps.supports("text") is True
        
    def test_parse_version_header(self):
        """X-Client-Version header should parse correctly"""
        caps = ClientCapabilities(version_header="1.5.0+42")
        
        assert caps.version == "1.5.0"
        assert caps.build == "42"
        
    def test_case_insensitive(self):
        """Component type matching should be case-insensitive"""
        caps = ClientCapabilities(header_value="Text;BUTTON;VStack")
        
        assert caps.supports("text") is True
        assert caps.supports("TEXT") is True
        assert caps.supports("button") is True
        assert caps.supports("vstack") is True


class TestLyoProtocolAdapter:
    """Tests for LyoProtocolAdapter filtering"""
    
    def test_supported_components_pass_through(self):
        """Supported components should pass through unchanged"""
        caps = ClientCapabilities(header_value="text;button;vstack")
        adapter = LyoProtocolAdapter(caps)
        
        components = [
            {"type": "text", "props": {"content": "Hello"}},
            {"type": "button", "props": {"label": "Click me"}}
        ]
        
        result = adapter.adapt(components)
        
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "button"
        
    def test_unsupported_creates_fallback(self):
        """Unsupported components should be replaced with fallback"""
        caps = ClientCapabilities(header_value="text;button")
        adapter = LyoProtocolAdapter(caps)
        
        components = [
            {"type": "hologram_3d", "props": {"text": "Future content"}}
        ]
        
        result = adapter.adapt(components)
        
        assert len(result) == 1
        assert result[0]["type"] == "fallback"
        assert result[0]["props"]["original_type"] == "hologram_3d"
        assert result[0]["props"]["fallback_text"] == "Future content"
        
    def test_fallback_count_tracked(self):
        """Adapter should track fallback count for telemetry"""
        caps = ClientCapabilities(header_value="text")
        adapter = LyoProtocolAdapter(caps)
        
        components = [
            {"type": "unknown1", "props": {}},
            {"type": "unknown2", "props": {}},
            {"type": "text", "props": {"content": "OK"}},
        ]
        
        result = adapter.adapt(components)
        
        assert adapter.fallback_count == 2
        assert len(adapter.fallback_types) == 2
        
    def test_nested_children_processed(self):
        """Children components should be processed recursively"""
        caps = ClientCapabilities(header_value="vstack;text")
        adapter = LyoProtocolAdapter(caps)
        
        components = [
            {
                "type": "vstack",
                "children": [
                    {"type": "text", "props": {"content": "Child 1"}},
                    {"type": "unknown_widget", "props": {"text": "Child 2"}},
                ]
            }
        ]
        
        result = adapter.adapt(components)
        
        assert len(result) == 1
        assert result[0]["type"] == "vstack"
        assert len(result[0]["children"]) == 2
        assert result[0]["children"][0]["type"] == "text"
        assert result[0]["children"][1]["type"] == "fallback"


class TestFilterConvenienceFunction:
    """Tests for filter_components_for_client utility"""
    
    def test_convenience_function_works(self):
        """filter_components_for_client should work correctly"""
        caps = ClientCapabilities(header_value="text;image")
        
        components = [
            {"type": "text", "props": {}},
            {"type": "hologram", "props": {"text": "3D View"}}
        ]
        
        result = filter_components_for_client(components, caps)
        
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
