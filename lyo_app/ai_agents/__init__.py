"""
LyoApp AI Agents Package

This package contains the complete AI system for LyoApp, including:
- Multi-agent AI orchestration
- Hybrid LLM routing (on-device Gemma + cloud LLM)
- Real-time sentiment analysis and engagement tracking
- Intelligent mentoring system
- Curriculum generation and content curation
- WebSocket-based real-time communication

The system is designed for enterprise-scale production use with:
- Comprehensive error handling and fallback mechanisms
- Performance monitoring and health checks
- Asynchronous processing via Celery
- Production-ready security and rate limiting
"""

from .orchestrator import AIOrchestrator, ai_orchestrator
from .mentor_agent import AIMentor, ai_mentor
from .sentiment_agent import SentimentAndEngagementAgent, sentiment_engagement_agent
from .websocket_manager import ConnectionManager, connection_manager
from .routes import router as ai_router

__version__ = "1.0.0"
__author__ = "LyoApp AI Team"

__all__ = [
    "AIOrchestrator",
    "AIMentor", 
    "SentimentAndEngagementAgent",
    "ConnectionManager",
    "ai_orchestrator",
    "ai_mentor",
    "sentiment_engagement_agent",
    "connection_manager",
    "ai_router"
]
