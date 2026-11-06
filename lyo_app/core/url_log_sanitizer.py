"""Remove request query strings before Uvicorn sends records to log handlers.

WebSocket authentication currently accepts a token in the URL query string.
Uvicorn logs accepted WebSocket URLs at INFO on ``uvicorn.error``, so a
middleware-only scrubber is too late: the ASGI server logs the handshake.

This filter intentionally removes the *whole* query string rather than trying
to maintain a list of credential parameter names.  That protects newly added
query credentials too, and keeps the route, client address, and status useful.
"""

from __future__ import annotations

import logging
import re
from typing import Any


# Request paths (including WebSocket paths) and full HTTP(S)/WS(S) URLs.
# Stop at common message/argument delimiters; do not retain any query value.
_REQUEST_URL_QUERY = re.compile(
    r"(?P<path>(?:(?:https?|wss?)://[^\s\"'<>/?#]+(?:/[^\s\"'<>?#]*)?"
    r"|/[^\s\"'<>?#]*))\?[^\s\"'<>]*",
    re.IGNORECASE,
)


def strip_request_url_queries(value: str) -> str:
    """Erase URL queries while preserving the URL path and unrelated text."""
    return _REQUEST_URL_QUERY.sub(lambda match: match.group("path"), value)


def _sanitize_argument(value: Any) -> Any:
    """Keep %-format logging arguments intact except URL-bearing strings."""
    if isinstance(value, str):
        return strip_request_url_queries(value)
    if isinstance(value, (bytes, bytearray)):
        sanitized = strip_request_url_queries(value.decode("utf-8", errors="replace"))
        return sanitized.encode("utf-8")
    if isinstance(value, tuple):
        return tuple(_sanitize_argument(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_argument(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_argument(item) for key, item in value.items()}
    return value


def _exception_chain_has_request_query(exception: BaseException) -> bool:
    """Catch secrets in exception causes even when the outer message is clean."""
    seen: set[int] = set()
    pending = [exception]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        message = str(current)
        if strip_request_url_queries(message) != message:
            return True
        for note in getattr(current, "__notes__", ()):
            if strip_request_url_queries(note) != note:
                return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


class RequestURLQueryFilter(logging.Filter):
    """Sanitize Uvicorn's structured access/error record before any formatter.

    Both plain-text and JSON handlers receive the already-scrubbed record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = strip_request_url_queries(record.msg)
        elif isinstance(record.msg, (bytes, bytearray)):
            record.msg = _sanitize_argument(record.msg)
        if record.args:
            record.args = _sanitize_argument(record.args)
        if record.exc_text:
            record.exc_text = strip_request_url_queries(record.exc_text)
        if record.stack_info:
            record.stack_info = strip_request_url_queries(record.stack_info)

        # The default formatter renders exception chains separately, bypassing
        # record.msg, and traceback *source lines* can contain literal URLs.
        # For URL-bearing exceptions, preserve the exception's class and safe
        # message, but never pass the original chain/traceback to the formatter.
        if record.exc_info and record.exc_info[1] is not None:
            original_type, original_exception, _ = record.exc_info
            if _exception_chain_has_request_query(original_exception):
                safe_exception = Exception(
                    f"{original_type.__name__}: "
                    f"{strip_request_url_queries(str(original_exception))}"
                )
                record.exc_info = (Exception, safe_exception, None)
                record.exc_text = None
        return True


_UVICORN_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
    "websockets.server",
    "websockets.protocol",
)


def install_request_url_query_filter() -> None:
    """Install exactly one filter per server logger, including WebSocket logs.

    Run this at application *import time*, before a handshake can be accepted.
    Lifespan startup is not early enough for server-level log setup.
    """
    for name in _UVICORN_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(f, RequestURLQueryFilter) for f in target.filters):
            target.addFilter(RequestURLQueryFilter())
