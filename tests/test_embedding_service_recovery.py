"""Permanent embedding authentication failures cannot stall each lesson turn."""

from unittest.mock import Mock

import pytest

from lyo_app.services import embedding_service as module


@pytest.mark.asyncio
async def test_leaked_embedding_key_is_not_retried_on_subsequent_queries(monkeypatch):
    monkeypatch.setattr(module.settings, "gemini_api_key", "test-key")
    embed = Mock(side_effect=RuntimeError(
        "403 Your API key was reported as leaked. Please use another API key."
    ))
    monkeypatch.setattr(module.genai, "embed_content", embed)
    service = module.EmbeddingService()

    assert await service.embed_query("fractions") is None
    assert await service.embed_query("geometry") is None
    assert await service.embed_text("lesson notes") is None
    assert embed.call_count == 1
