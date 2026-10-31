"""Static course v2 endpoints must never be shadowed by a dynamic ID route."""

import ast
from pathlib import Path


def test_static_routes_precede_dynamic_course_id():
    source = (
        Path(__file__).resolve().parents[1]
        / "lyo_app"
        / "ai_agents"
        / "multi_agent_v2"
        / "routes.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    routes = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            path = decorator.args[0].value
            if path in {"/{job_id_or_course_id}", "/jobs", "/health", "/config", "/regenerate"}:
                routes[path] = node.lineno

    assert len(routes) == 5
    for literal in ("/jobs", "/health", "/config", "/regenerate"):
        assert routes[literal] < routes["/{job_id_or_course_id}"]


def test_health_request_reaches_health_handler_instead_of_course_lookup():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from lyo_app.ai_agents.multi_agent_v2.routes import router

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/v2/courses/health")

    assert response.status_code == 200
    assert response.json()["service"] == "course-generation-v2"
