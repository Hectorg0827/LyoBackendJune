from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from lyo_app.enhanced_main import create_app


def test_native_classroom_analytics_route_is_mounted_at_client_path():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/classroom/analytics/event" in paths


def test_native_classroom_analytics_event_is_accepted():
    app = create_app()
    with patch(
        "lyo_app.classroom.analytics.analytics_service.track_interaction",
        new=AsyncMock(),
    ) as track:
        response = TestClient(app).post(
            "/api/v1/classroom/analytics/event",
            json={
                "event_type": "quiz_answered",
                "card_id": "check-1",
                "topic": "fractions",
                "is_correct": True,
            },
        )

    assert response.status_code == 200
    track.assert_awaited_once()
    assert track.await_args.kwargs["event_type"] == "quiz_answered"
    assert track.await_args.kwargs["card_id"] == "check-1"
