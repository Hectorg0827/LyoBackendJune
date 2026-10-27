"""Sentry starts from SENTRY_DSN and reports the ENVIRONMENT.

The settings object enhanced_main uses had no SENTRY_DSN field, so the old
check (hasattr(settings, "SENTRY_DSN")) was always false and Sentry never
started, even with the variable set.
"""
from lyo_app import enhanced_main


def test_sentry_starts_from_sentry_dsn_with_the_environment(monkeypatch):
    captured = {}
    monkeypatch.setattr(enhanced_main.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(enhanced_main.settings, "SENTRY_DSN", "https://key@o0.ingest.sentry.io/0")
    monkeypatch.setattr(enhanced_main.settings, "ENVIRONMENT", "production")
    assert enhanced_main._init_sentry() is True
    assert captured["dsn"] == "https://key@o0.ingest.sentry.io/0"
    assert captured["environment"] == "production"


def test_sentry_stays_off_without_a_dsn(monkeypatch):
    monkeypatch.setattr(enhanced_main.sentry_sdk, "init", lambda **_: (_ for _ in ()).throw(AssertionError("started")))
    monkeypatch.setattr(enhanced_main.settings, "SENTRY_DSN", None)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert enhanced_main._init_sentry() is False


def test_the_settings_read_sentry_dsn_from_the_environment(monkeypatch):
    from lyo_app.core.enhanced_config import EnhancedSettings

    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    assert EnhancedSettings().SENTRY_DSN == "https://key@o0.ingest.sentry.io/1"
