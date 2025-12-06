"""
LYO Image Generation Module
DALL-E 3 integration for rich educational visuals
"""

from .service import ImageService
from .routes import router as image_router

__all__ = ["ImageService", "image_router"]
