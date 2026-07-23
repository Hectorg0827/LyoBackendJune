"""Bootstrap canonical learning routes into both versioned and legacy mounts."""

from lyo_app.learning.progress_routes import router
from lyo_app.learning import routes as legacy_routes

# enhanced_main mounts legacy_routes.router later at /learning and /api/v1/learning.
# Prepending here makes the canonical handlers win route matching while retaining
# all legacy endpoints that do not overlap.
legacy_routes.router.routes = list(router.routes) + list(legacy_routes.router.routes)

__all__ = ["router"]
