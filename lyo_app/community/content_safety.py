"""Validation for user-authored Community content.

Every client renders Community text as plain text, so the safest stored form
is plain text: markup is stripped (repeatedly, so entity-encoded tags cannot
survive a decode), and links must be ordinary web URLs.
"""

from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import urlparse

import bleach

_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_WHITESPACE_RUN = re.compile(r"[ \t\f\v]+")
_TAG_LIKE = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
MAX_LINKS_IN_DESCRIPTION = 3


def plain_text(value: Optional[str], *, multiline: bool = False) -> Optional[str]:
    """Strip markup and scripts, keeping readable characters like ``&`` and ``<``."""
    if value is None:
        return None
    text = str(value)
    # Decode-then-strip until stable so entity-encoded tags cannot survive.
    for _ in range(4):
        cleaned = html.unescape(bleach.clean(text, tags=[], strip=True, strip_comments=True))
        if cleaned == text:
            break
        text = cleaned
    text = _TAG_LIKE.sub("", text)
    if multiline:
        lines = [_WHITESPACE_RUN.sub(" ", line).strip() for line in text.splitlines()]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = " ".join(text.split())
    return text.strip() or None


def safe_web_url(value: Optional[str]) -> Optional[str]:
    """Return a normalized http(s) URL, or raise ``ValueError``."""
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    if candidate.lower().startswith("www."):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Links must start with http:// or https://")
    if any(character.isspace() for character in candidate) or "<" in candidate or ">" in candidate:
        raise ValueError("Links cannot contain spaces or markup")
    return candidate


def link_count(value: Optional[str]) -> int:
    return len(_URL_PATTERN.findall(value or ""))


def ensure_not_link_spam(description: Optional[str]) -> None:
    if link_count(description) > MAX_LINKS_IN_DESCRIPTION:
        raise ValueError(
            f"Descriptions can include at most {MAX_LINKS_IN_DESCRIPTION} links"
        )
