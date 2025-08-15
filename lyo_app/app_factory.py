from fastapi import FastAPI
from .routers import auth, media, feed, stories, messaging, notifications, tutor, planner, practice, resources, search, moderation, admin

def create_app() -> FastAPI:
    app = FastAPI(title="Lyo API", version="1.0.0")
    @app.get("/healthz")
    async def healthz():
        return {"ok": True}
    v1 = "/v1"
    app.include_router(auth.router,         prefix=v1)
    app.include_router(media.router,        prefix=v1)
    app.include_router(feed.router,         prefix=v1)
    app.include_router(stories.router,      prefix=v1)
    app.include_router(messaging.router,    prefix=v1)
    app.include_router(notifications.router,prefix=v1)
    app.include_router(tutor.router,        prefix=v1)
    app.include_router(planner.router,      prefix=v1)
    app.include_router(practice.router,     prefix=v1)
    app.include_router(resources.router,    prefix=v1)
    app.include_router(search.router,       prefix=v1)
    app.include_router(moderation.router,   prefix=v1)
    app.include_router(admin.router,        prefix=v1)
    return app
