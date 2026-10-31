"""Disabled Voice Lab smoke tests. Never call a paid provider."""
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lyo_app.live_trial import staging_app


def _staging_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/voice_lab")
    monkeypatch.setenv("LYO_GPT_LIVE_TRIAL_ENABLED", "false")
    for key in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID",
                "RAILWAY_ENVIRONMENT_NAME"):
        monkeypatch.delenv(key, raising=False)


def test_voice_lab_exposes_only_trial_endpoints_and_health():
    paths = {route.path for route in staging_app.app.routes}
    assert paths == {
        "/healthz",
        "/api/v1/gpt-live-trial/status",
        "/api/v1/gpt-live-trial/ticket",
        "/api/v1/gpt-live-trial/stream",
    }
    assert "/auth/login" not in paths
    assert "/clips" not in paths



def test_unpaid_http_and_websocket_denial_without_startup(monkeypatch):
    _staging_env(monkeypatch)
    client = TestClient(staging_app.app)
    assert client.get("/healthz").json() == {
        "status": "ok", "service": "lyo-voice-lab", "paid_gpt_live": False,
    }
    status = client.get("/api/v1/gpt-live-trial/status")
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "cap_usd": "10.00", "session_seconds": 60}
    ticket = client.post("/api/v1/gpt-live-trial/ticket")
    assert ticket.status_code == 403
    assert "disabled" in ticket.json()["detail"]
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/api/v1/gpt-live-trial/stream"):
            pass
    assert closed.value.code == 1008


@pytest.mark.parametrize("value", ["true", "1", "on"])
def test_any_paid_flag_blocks_startup(monkeypatch, value):
    _staging_env(monkeypatch)
    monkeypatch.setenv("LYO_GPT_LIVE_TRIAL_ENABLED", value)
    with pytest.raises(RuntimeError, match="not approved"):
        staging_app.validate_staging_runtime()


@pytest.mark.parametrize("bad_database", ["", "sqlite+aiosqlite:///./trial.db"])
def test_no_durable_postgres_means_startup_fails(monkeypatch, bad_database):
    _staging_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", bad_database)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        staging_app.validate_staging_runtime()


@pytest.mark.parametrize("key,bad_value", [
    ("ENVIRONMENT", "production"),
    ("RAILWAY_ENVIRONMENT_NAME", "production"),
    ("RAILWAY_PROJECT_ID", "wrong-project"),
    ("RAILWAY_ENVIRONMENT_ID", "wrong-environment"),
    ("RAILWAY_SERVICE_ID", "wrong-service"),
])
def test_wrong_deployment_scope_rejected(monkeypatch, key, bad_value):
    _staging_env(monkeypatch)
    monkeypatch.setenv(key, bad_value)
    with pytest.raises(RuntimeError, match="staging|scope mismatch"):
        staging_app.validate_staging_runtime()


@pytest.mark.asyncio
async def test_isolated_lifespan_pings_database_and_initializes_only_ledger(monkeypatch):
    _staging_env(monkeypatch)
    events = []

    @asynccontextmanager
    async def fake_connection():
        class Connection:
            async def execute(self, statement):
                events.append(str(statement))
        yield Connection()

    engine = SimpleNamespace(connect=fake_connection)

    async def fake_initialize_schema(actual_engine):
        assert actual_engine is engine
        events.append("ledger_initialized")

    monkeypatch.setattr(staging_app, "engine", engine)
    monkeypatch.setattr(staging_app, "initialize_schema", fake_initialize_schema)
    async with staging_app.lifespan(staging_app.app):
        assert events == ["SELECT 1", "ledger_initialized"]
