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
