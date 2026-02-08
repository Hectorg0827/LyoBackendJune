"""
Lyo Temporal Module - Durable Workflows for AI Operations

This module provides crash-resistant, auto-retry workflows for:
- Course generation
- Lesson content generation
- Chat sessions

Architecture:
- activities/: Individual units of work (wrap existing agents)
- workflows/: Orchestration of activities
- schemas/: Pydantic models for constrained AI generation
- client.py: Temporal client singleton
"""

from .client import get_temporal_client

__all__ = ["get_temporal_client"]
