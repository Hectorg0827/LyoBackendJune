"""Discover's tabs must be genuine database queries, not decorative labels."""
from sqlalchemy.dialects import postgresql

from lyo_app.routers.clips import _search_clips, _discover_order, router
from lyo_app.models.clips import Clip


def test_search_is_literal_and_uses_all_supported_fields():
    expression = _search_clips("  100%_Math  ")
    rendered = expression.compile(dialect=postgresql.dialect())
    query = str(rendered)
    assert "lower(clips.title)" in query
    assert "lower(clips.description)" in query
    assert "lower(clips.subject)" in query
    assert "lower(clips.topic)" in query
    assert any("100/%/_math" in str(value) for value in rendered.params.values())
    assert _search_clips("   ") is None


def test_sort_options_are_stable_and_meaningfully_distinct():
    latest = str(Clip.__table__.select().order_by(*_discover_order("latest")).compile())
    popular = str(Clip.__table__.select().order_by(*_discover_order("popular")).compile())
    default = str(Clip.__table__.select().order_by(*_discover_order("for_you")).compile())
    assert "created_at DESC" in latest
    assert "like_count DESC" in popular
    assert "view_count + clips.like_count" in default
    assert latest != popular != default


def test_literal_filter_and_saved_routes_exist():
    registered = {route.path for route in router.routes}
    assert "/clips/discover/filters" in registered
    assert "/clips/discover" in registered
    assert "/clips/saved" in registered
