"""
Config-consistency tests.

The codebase still has multiple live settings modules (core.config,
core.settings, core.enhanced_config). Until they are fully unified these
tests pin the invariants that keep them from drifting apart in dangerous
ways — most importantly that all JWT signing paths derive their secret from
the same environment variable and agree on token lifetime, and that
production refuses to boot with known-insecure secrets.
"""

import importlib
import os

import pytest


def _fresh(module_name: str, env: dict):
    """(Re)import a settings module under a controlled environment."""
    old = {k: os.environ.get(k) for k in env}
    os.environ.update({k: v for k, v in env.items() if v is not None})
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
    try:
        mod = importlib.import_module(module_name)
        return importlib.reload(mod)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


STRONG = "a-strong-test-secret-key-that-is-long-enough-42chars"


def test_jwt_secret_falls_back_to_secret_key():
    """Setting only SECRET_KEY must secure the JWT signing path too."""
    mod = _fresh(
        "lyo_app.core.settings",
        {"ENVIRONMENT": "development", "SECRET_KEY": STRONG, "JWT_SECRET_KEY": None},
    )
    assert mod.settings.JWT_SECRET_KEY == STRONG


def test_explicit_jwt_secret_wins():
    mod = _fresh(
        "lyo_app.core.settings",
        {
            "ENVIRONMENT": "development",
            "SECRET_KEY": STRONG,
            "JWT_SECRET_KEY": STRONG + "-jwt",
        },
    )
    assert mod.settings.JWT_SECRET_KEY == STRONG + "-jwt"


def test_production_refuses_insecure_jwt_secret():
    with pytest.raises(Exception, match="insecure token secrets"):
        _fresh(
            "lyo_app.core.settings",
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "dev_secret_key",
                "JWT_SECRET_KEY": None,
            },
        )


def test_production_boots_with_strong_secret():
    mod = _fresh(
        "lyo_app.core.settings",
        {"ENVIRONMENT": "production", "SECRET_KEY": STRONG, "JWT_SECRET_KEY": None},
    )
    assert mod.settings.JWT_SECRET_KEY == STRONG


def test_token_expiry_policy_agrees_across_config_modules():
    """All settings modules must share one access-token lifetime policy."""
    env = {"ENVIRONMENT": "development", "SECRET_KEY": STRONG, "JWT_SECRET_KEY": None}
    core_settings = _fresh("lyo_app.core.settings", env).settings
    core_config = _fresh("lyo_app.core.config", env).settings
    enhanced = _fresh("lyo_app.core.enhanced_config", env).settings

    assert core_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 60
    assert core_config.access_token_expire_minutes == 60
    assert enhanced.ACCESS_TOKEN_EXPIRE_MINUTES == 60

    assert core_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 30
    assert core_config.refresh_token_expire_days == 30
    assert enhanced.REFRESH_TOKEN_EXPIRE_DAYS == 30


def test_removed_config_modules_stay_removed():
    """Dead config variants must not quietly come back."""
    with pytest.raises(ImportError):
        importlib.import_module("lyo_app.core.production_config")
