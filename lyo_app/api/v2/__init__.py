"""API v2 Package"""

from lyo_app.api.v2.courses import router as courses_router
from lyo_app.api.v2.audio import router as audio_router
from lyo_app.api.v2.course_generator_routes import router as generator_router

__all__ = ["courses_router", "audio_router", "generator_router"]
