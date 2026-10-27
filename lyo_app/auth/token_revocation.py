"""Targeted emergency JWT revocation without rotating other learners' keys."""

import os
from typing import Any, Mapping


def is_token_revoked(payload: Mapping[str, Any]) -> bool:
    """Read the deployment's comma-separated revoked JWT IDs on every check.

    JWT IDs are identifiers, not credentials. Never put the exposed token in
    this setting. Keeping this check outside the validation cache prevents
    cached tokens from bypassing revocation.
    """
    revoked = {
        value.strip()
        for value in os.getenv("JWT_REVOKED_JTIS", "").split(",")
        if value.strip()
    }
    return bool(payload.get("jti") and str(payload["jti"]) in revoked)
