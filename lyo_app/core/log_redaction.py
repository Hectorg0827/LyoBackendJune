"""Remove credentials before any Python log handler can format a record."""

import logging
import re
import traceback
from typing import Any


_QUERY = re.compile(r"(\?)[^\s\"'<>]*")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_CREDENTIAL = re.compile(
    r"((?:access_token|refresh_token|token|api_key|ticket|authorization)"
    r"[\"']?\s*[:=]\s*[\"']?)[^\s,;&\"'}]+",
    re.IGNORECASE,
)
_SECRET_KEYS = {"access_token", "refresh_token", "token", "api_key", "ticket", "authorization"}


def redact_log_text(value: str) -> str:
    # Drop the whole query, including encoded credential keys, rather than
    # trying to enumerate every spelling in server access messages.
    value = _QUERY.sub(r"\1[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED]", value)
    return _CREDENTIAL.sub(r"\1[REDACTED]", value)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_log_text(value)
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    return value


def install_log_redaction() -> None:
    """Cover non-propagating Uvicorn loggers and future handler replacement.

    WebSocket accepts/rejects use uvicorn.error, not uvicorn.access. A filter
    only on the root logger, or --no-access-log, does not cover that path.
    Preserve the original args shape for Uvicorn's AccessFormatter.
    """
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_lyo_redacts_credentials", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # AccessFormatter unpacks these five fields before formatting.
            record.args = _redact(record.args)
        else:
            # Render first: dropping a query containing a %s placeholder while
            # keeping args would cause logging's error fallback to print them.
            record.args = _redact(record.args)
            record.msg = redact_log_text(record.getMessage())
            record.args = ()
        if record.exc_info:
            record.exc_text = redact_log_text(
                "".join(traceback.format_exception(*record.exc_info))
            )
            record.exc_info = None
        if record.stack_info:
            record.stack_info = redact_log_text(record.stack_info)
        return record

    factory._lyo_redacts_credentials = True
    logging.setLogRecordFactory(factory)
