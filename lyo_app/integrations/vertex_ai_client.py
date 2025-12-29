"""Minimal Vertex AI wrapper (lazy) to report availability.
This does not perform calls yet; only checks environment and library presence.
"""
from __future__ import annotations
import os
from typing import Optional

try:
    from google.cloud import aiplatform  # type: ignore
    _VERTEX_AVAILABLE = True
except Exception:  # pragma: no cover
    _VERTEX_AVAILABLE = False

class VertexAIClient:
    def __init__(self):
        self._enabled = False
        self._initialized_sdk = False

    def initialize_app(self):
        if self._initialized_sdk:
            return
        self._initialized_sdk = True

        if not _VERTEX_AVAILABLE:
            return
        try:
            project = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("VERTEX_AI_REGION", "us-central1")
            # aiplatform.init can be blocking if it checks auth
            if project:
                aiplatform.init(project=project, location=location)
                self._enabled = True
        except Exception:
            self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

vertex_ai_client = VertexAIClient()


def get_vertex_ai_client():
    """Get Vertex AI client instance"""
    return vertex_ai_client
