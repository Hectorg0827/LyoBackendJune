"""Explicit staging services only; production and arbitrary Railway apps fail closed."""
import os
import re
from urllib.parse import urlsplit

DEFAULT_BACKEND = "https://lyojourneystagingbackend-staging.up.railway.app"
DEFAULT_WEB = "https://lyoonestagingweb-staging.up.railway.app"


def approved_staging_origin(value: str, *, web: bool = False) -> bool:
    parts = urlsplit(value)
    default = DEFAULT_WEB if web else DEFAULT_BACKEND
    prefix = "lyolaunchweb" if web else "lyolaunchbackend"
    return bool(
        parts.scheme == "https" and not parts.username and not parts.password
        and parts.path in ("", "/") and not parts.query and not parts.fragment
        and parts.netloc == parts.hostname
        and (value.rstrip("/") == default or re.fullmatch(
            prefix + r"-staging(?:-[a-z0-9]+)?\.up\.railway\.app", parts.hostname or ""))
    )


def staging_origin(*, web: bool = False) -> str:
    key = "LYO_ONE_STAGING_WEB_URL" if web else "LYO_ONE_STAGING_BACKEND_URL"
    value = os.getenv(key, DEFAULT_WEB if web else DEFAULT_BACKEND).rstrip("/")
    if not approved_staging_origin(value, web=web):
        raise ValueError("Refusing a non-isolated staging origin")
    return value
