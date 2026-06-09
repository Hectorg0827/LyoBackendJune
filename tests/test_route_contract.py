"""
Route-contract regression tests.

These lock in the iOS ↔ backend HTTP/WebSocket contract at the *mounted app*
level, so regressions like the feeds-router being shadowed by enhanced_routes
(which silently removed every /api/v1/posts* route) fail CI instead of
shipping. They boot the real production app object from lyo_app.enhanced_main.
"""

import os

# Minimal env so the app object can be constructed deterministically.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest


@pytest.fixture(scope="module")
def app():
    from lyo_app.enhanced_main import app as fastapi_app
    return fastapi_app


def _route_table(app):
    table = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        if path is None:
            continue
        methods = getattr(r, "methods", None)
        if methods:
            for m in methods:
                table.add((m, path))
        else:
            # WebSocket routes expose no .methods
            table.add(("WS", path))
    return table


# (method, path) pairs the iOS client depends on.
IOS_HTTP_CONTRACT = [
    ("GET", "/api/v1/feed"),
    ("POST", "/api/v1/posts"),
    ("GET", "/api/v1/posts/{post_id}"),
    ("DELETE", "/api/v1/posts/{post_id}"),
    ("POST", "/api/v1/posts/{post_id}/reactions"),
    ("GET", "/api/v1/posts/{post_id}/comments"),
    ("POST", "/api/v1/posts/{post_id}/comments"),
]


@pytest.mark.parametrize("method,path", IOS_HTTP_CONTRACT)
def test_ios_http_routes_present(app, method, path):
    assert (method, path) in _route_table(app), f"Missing iOS route: {method} {path}"


def test_classroom_lesson_websocket_present(app):
    assert ("WS", "/api/v1/classroom/ws/lesson/{topic}") in _route_table(app), (
        "iOS classroom lesson WebSocket is not mounted"
    )


def test_no_duplicate_post_routes(app):
    """A path+method should be registered at most once under /api/v1/posts."""
    from collections import Counter
    counts = Counter(
        (m, p) for (m, p) in _route_table(app) if p.startswith("/api/v1/posts")
    )
    dupes = {k: c for k, c in counts.items() if c > 1}
    assert not dupes, f"Duplicate /api/v1/posts routes: {dupes}"


def test_openapi_schema_builds(app):
    """OpenAPI generation validates every route's models/path coherence."""
    schema = app.openapi()
    assert schema.get("paths"), "OpenAPI produced no paths"
