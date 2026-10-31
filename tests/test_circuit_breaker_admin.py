"""The maintenance reset must never be callable by guests or ordinary users."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from lyo_app.auth.admin_dependencies import require_superuser_for_circuit_reset
from lyo_app.auth.dependencies import get_current_user, get_db


def _protected_test_app(reset):
    app = FastAPI()

    @app.post("/admin/reset-circuit-breakers", dependencies=[Depends(require_superuser_for_circuit_reset)])
    async def endpoint():
        reset()
        return {"status": "ok"}

    return app


def test_production_reset_route_has_superuser_dependency():
    """Verify the actual route is wired to the guarded dependency."""
    path = Path(__file__).resolve().parents[1] / "lyo_app" / "enhanced_main.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    endpoints = [
        node for node in ast.walk(module)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "reset_circuit_breakers"
    ]
    assert len(endpoints) == 1
    decorators = " ".join(ast.unparse(item) for item in endpoints[0].decorator_list)
    assert "Depends(require_superuser_for_circuit_reset)" in decorators


def test_anonymous_cannot_reset_circuit_breakers():
    reset = Mock()
    app = _protected_test_app(reset)
    response = TestClient(app).post("/admin/reset-circuit-breakers")
    assert response.status_code in (401, 403)
    reset.assert_not_called()


def test_authenticated_non_admin_cannot_reset_circuit_breakers():
    reset = Mock()
    app = _protected_test_app(reset)
    db = SimpleNamespace(scalar=AsyncMock(return_value=False))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, is_active=True)
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post("/admin/reset-circuit-breakers")

    assert response.status_code == 403
    reset.assert_not_called()
    db.scalar.assert_awaited_once()


def test_authenticated_database_superuser_can_reset():
    reset = Mock()
    app = _protected_test_app(reset)
    db = SimpleNamespace(scalar=AsyncMock(return_value=True))
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, is_active=True)
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post("/admin/reset-circuit-breakers")

    assert response.status_code == 200
    reset.assert_called_once()
    db.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_inactive_superuser_is_denied_before_database_check():
    db = SimpleNamespace(scalar=AsyncMock(return_value=True))
    with pytest.raises(HTTPException) as exc_info:
        await require_superuser_for_circuit_reset(
            current_user=SimpleNamespace(id=7, is_active=False), db=db
        )
    assert exc_info.value.status_code == 403
    db.scalar.assert_not_awaited()
