"""Bootstrap canonical learning routes into both versioned and legacy mounts."""

from lyo_app.learning.progress_routes import router
from lyo_app.learning import routes as legacy_routes

# enhanced_main mounts legacy_routes.router at /learning and /api/v1/learning.
# FastAPI route matching is ordered, not type-aware: /courses/{course_id}
# would otherwise consume /courses/mine and return 422 before Saved loads.
# Preserve the static authenticated Saved route first, followed by canonical
# playback/progress, followed by all remaining legacy routes. The canonical
# detail handler must continue enforcing private draft ownership.
saved_routes = [
    route for route in legacy_routes.router.routes
    if getattr(route, "path", None) == "/courses/mine"
    and "GET" in getattr(route, "methods", set())
]
remaining_routes = [
    route for route in legacy_routes.router.routes if route not in saved_routes
]
# api/v1 mounts the exported canonical router before enhanced_main mounts the
# legacy one, so Saved must lead BOTH route lists. Otherwise the earlier
# /courses/{course_id} consumes the literal "mine" and returns HTTP 422.
router.routes = saved_routes + list(router.routes)
legacy_routes.router.routes = list(router.routes) + remaining_routes

__all__ = ["router"]
