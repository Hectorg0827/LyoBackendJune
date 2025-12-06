"""
LYO Text-to-Speech Module
Award-winning AI classroom experience with premium voices
"""

from .service import TTSService
from .routes import router as tts_router

__all__ = ["TTSService", "tts_router"]
