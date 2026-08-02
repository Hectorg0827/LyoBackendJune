"""Validation and model preparation for Lyo chat attachments.

Only files uploaded through Lyo's own authenticated ``/api/v1/media/upload``
route are accepted.  Resolving those URLs to local storage avoids arbitrary
server-side URL fetching and keeps the multimodal path SSRF-safe.
"""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, status

from lyo_app.ai.schemas.lyo2 import InputModality, MediaRef
from lyo_app.core.config import settings

MAX_CHAT_ATTACHMENTS = 4
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024

ALLOWED_CHAT_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}

_FOLDER_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_MEDIA_PREFIX = "/api/v1/media/file/"
_CANONICAL_ATTACHMENT_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)]+)\)|\[📎 ([^\]]+)\]\(([^)]+)\)"
)
_EXTENSION_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
}


def _clean_label(value: str) -> str:
    label = _SAFE_NAME_RE.sub("", value).strip().replace("[", "").replace("]", "")
    label = label.replace("(", "").replace(")", "")
    return label[:120] or "Attachment"


def _local_media_path(uri: str) -> Path:
    parsed = urlparse(uri)
    path = unquote(parsed.path if parsed.scheme else uri.split("?", 1)[0])
    if not path.startswith(_MEDIA_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat attachments must be uploaded through Lyo before sending.",
        )

    relative = path[len(_MEDIA_PREFIX):]
    pieces = relative.split("/")
    if len(pieces) != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment path")
    folder, filename = pieces
    if (
        not _FOLDER_RE.fullmatch(folder)
        or folder != "chat"
        or not filename
        or filename.startswith(".")
        or "/" in filename
        or ".." in filename
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment path")

    root = (Path(getattr(settings, "upload_dir", None) or "uploads") / "media").resolve()
    candidate = (root / folder / filename).resolve()
    if root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment path")
    return candidate


def canonical_message_content(text: str | None, media: Iterable[MediaRef]) -> str:
    """Persist attachments as portable Markdown while keeping model input structured."""
    parts: List[str] = []
    if text and text.strip():
        parts.append(text.strip())

    for item in media:
        parsed_name = Path(unquote(urlparse(item.uri).path)).name
        label = _clean_label(item.name or parsed_name)
        if item.modality == InputModality.IMAGE:
            parts.append(f"![{label}]({item.uri})")
        else:
            parts.append(f"[📎 {label}]({item.uri})")
    return "\n\n".join(parts)


def recent_media_refs(conversation_history: Iterable[Any]) -> List[MediaRef]:
    """Recover the latest attachment-bearing user turn for follow-up questions.

    The database stores portable Markdown rather than base64.  Re-resolving only
    Lyo-owned ``chat`` URLs lets a learner ask "what about question 2?" on a
    later turn or another device without allowing arbitrary URL fetches.
    """
    turns = list(conversation_history)[-8:]
    for turn in reversed(turns):
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", None)
        content = turn.get("content", "") if isinstance(turn, dict) else getattr(turn, "content", "")
        if role != "user" or not content:
            continue

        refs: List[MediaRef] = []
        seen = set()
        for match in _CANONICAL_ATTACHMENT_RE.finditer(content):
            image_uri, file_uri = match.group(2), match.group(4)
            uri = image_uri or file_uri or ""
            parsed = urlparse(uri)
            if not parsed.path.startswith(f"{_MEDIA_PREFIX}chat/") or uri in seen:
                continue
            seen.add(uri)
            is_image = bool(image_uri)
            name = match.group(1) if is_image else match.group(3)
            mime_type = _EXTENSION_MIME_TYPES.get(
                Path(unquote(parsed.path)).suffix.lower(),
                "image/jpeg" if is_image else "text/plain",
            )
            refs.append(
                MediaRef(
                    modality=InputModality.IMAGE if is_image else InputModality.DOCUMENT,
                    uri=uri,
                    mime_type=mime_type,
                    name=_clean_label(name or Path(unquote(parsed.path)).name),
                )
            )
            if len(refs) == MAX_CHAT_ATTACHMENTS:
                break
        if refs:
            return refs
    return []


async def load_media_attachments(
    media: List[MediaRef], *, missing_ok: bool = False
) -> List[Dict[str, Any]]:
    """Return Gemini inline-data parts after validating every local attachment."""
    if not media:
        return []
    if len(media) > MAX_CHAT_ATTACHMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Attach at most {MAX_CHAT_ATTACHMENTS} files per message.",
        )

    prepared: List[Dict[str, Any]] = []
    total_size = 0
    for item in media:
        mime_type = (item.mime_type or "").split(";", 1)[0].strip().lower()
        if mime_type not in ALLOWED_CHAT_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported chat attachment type '{mime_type}'.",
            )

        path = _local_media_path(item.uri)
        try:
            stat = await asyncio.to_thread(path.stat)
        except FileNotFoundError as exc:
            if missing_ok:
                continue
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="The attachment is no longer available. Please upload it again.",
            ) from exc

        if stat.st_size > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Each chat attachment must be 10MB or smaller.",
            )
        total_size += stat.st_size
        if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Chat attachments may total at most 20MB per message.",
            )

        data = await asyncio.to_thread(path.read_bytes)
        prepared.append(
            {
                "type": "media_base64",
                "mime_type": mime_type,
                "data": base64.b64encode(data).decode("ascii"),
                "name": _clean_label(item.name or path.name),
            }
        )
    return prepared
