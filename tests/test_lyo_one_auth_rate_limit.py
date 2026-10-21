"""Regression: navigating Lyo One must not consume login brute-force quota."""
from fastapi import FastAPI

from lyo_app.core.rate_limiter import InMemoryRateLimiter
from lyo_app.middleware.security_middleware import SecurityMiddleware


def _middleware():
    middleware = SecurityMiddleware(
        FastAPI(), enable_rate_limiting=True,
        enable_audit_logging=False, enable_security_headers=False,
    )
    middleware._rate_limiter = InMemoryRateLimiter()
    return middleware


def test_general_api_reads_cannot_lock_out_authenticated_profile_refresh():
    gate = _middleware()
    ip = "synthetic-learner-1"
    for _ in range(75):
        assert gate._check_rate_limit(ip, "/api/v1/me/coach/today", "GET")
    for _ in range(25):
        assert gate._check_rate_limit(ip, "/api/v1/auth/me", "GET")
    # A normal lesson-to-exam transition still has room to authenticate.
    assert gate._check_rate_limit(ip, "/api/v1/auth/login", "POST")


def test_credential_attempts_remain_strictly_throttled_separately():
    gate = _middleware()
    ip = "synthetic-learner-2"
    for _ in range(10):
        assert gate._check_rate_limit(ip, "/api/v1/auth/login", "POST")
    assert not gate._check_rate_limit(ip, "/api/v1/auth/register", "POST")
    # Even with a blocked credential bucket, the user can read their
    # already-authenticated profile and retain their current session.
    assert gate._check_rate_limit(ip, "/api/v1/auth/me", "GET")
    assert gate._check_rate_limit(ip, "/api/v1/me/study_plans/state", "GET")


def test_one_busy_learner_does_not_block_another_ip():
    gate = _middleware()
    for _ in range(10):
        assert gate._check_rate_limit("learner-a", "/api/v1/auth/login", "POST")
    assert not gate._check_rate_limit("learner-a", "/api/v1/auth/login", "POST")
    assert gate._check_rate_limit("learner-b", "/api/v1/auth/login", "POST")


def test_ai_general_and_auth_buckets_do_not_interfere():
    gate = _middleware()
    ip = "synthetic-learner-3"
    for _ in range(60):
        assert gate._check_rate_limit(ip, "/api/v1/ai/chat", "POST")
    assert not gate._check_rate_limit(ip, "/api/v1/ai/chat", "POST")
    assert gate._check_rate_limit(ip, "/api/v1/auth/me", "GET")
    assert gate._check_rate_limit(ip, "/api/v1/auth/login", "POST")
    assert gate._check_rate_limit(ip, "/api/v1/me/coach/today", "GET")
