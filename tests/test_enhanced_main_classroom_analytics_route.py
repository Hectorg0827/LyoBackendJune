"""The Railway production entrypoint must expose native classroom telemetry.

app_factory.py already mounted this router, but production boots
lyo_app.enhanced_main:app. Keep the contract pinned to the actual entrypoint so
client analytics cannot silently become 404 again.
"""


def test_production_entrypoint_mounts_classroom_analytics(monkeypatch):
    # enhanced_main creates its FastAPI app at import time. The CI environment
    # supplies the same required settings as the rest of the backend suite.
    from lyo_app.enhanced_main import app

    paths = {
        getattr(route, "path", None)
        for route in app.routes
    }
    assert "/api/v1/classroom/analytics/event" in paths
