from unittest.mock import Mock

import lyo_app.cache.course_cache as course_cache_module


def test_course_cache_uses_deployed_redis_url(monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "redis://shared-redis:6379/0")
    monkeypatch.setattr(course_cache_module, "REDIS_AVAILABLE", True)

    client = Mock()
    client.ping.return_value = True
    from_url = Mock(return_value=client)
    monkeypatch.setattr(course_cache_module.redis, "from_url", from_url)

    cache = course_cache_module.CourseSemanticCache(
        fallback_dir=str(tmp_path / "fallback")
    )

    from_url.assert_called_once_with(
        "redis://shared-redis:6379/0",
        decode_responses=True,
    )
    assert cache.use_redis is True
    assert cache.redis_url == "redis://shared-redis:6379/0"


def test_course_cache_does_not_invent_localhost_redis(monkeypatch, tmp_path):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(course_cache_module, "REDIS_AVAILABLE", True)

    from_url = Mock()
    monkeypatch.setattr(course_cache_module.redis, "from_url", from_url)

    fallback = tmp_path / "fallback"
    cache = course_cache_module.CourseSemanticCache(fallback_dir=str(fallback))

    from_url.assert_not_called()
    assert cache.use_redis is False
    assert cache.redis_url is None
    assert fallback.is_dir()


def test_explicit_redis_url_overrides_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6379/0")
    monkeypatch.setattr(course_cache_module, "REDIS_AVAILABLE", True)

    client = Mock()
    client.ping.return_value = True
    from_url = Mock(return_value=client)
    monkeypatch.setattr(course_cache_module.redis, "from_url", from_url)

    cache = course_cache_module.CourseSemanticCache(
        redis_url="redis://explicit:6379/0",
        fallback_dir=str(tmp_path / "fallback"),
    )

    from_url.assert_called_once_with(
        "redis://explicit:6379/0",
        decode_responses=True,
    )
    assert cache.redis_url == "redis://explicit:6379/0"
