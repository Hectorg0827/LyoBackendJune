"""Validation and model preparation for Lyo AI attachments.

Only files uploaded through Lyo's own authenticated ``/api/v1/media/upload``
route are accepted. Resolving those URLs to server-owned storage avoids
arbitrary URL fetching and keeps the multimodal path SSRF-safe.

The same loader is shared by Chat, Test Prep, and Classroom entry points.
"""

from __future__ import annotations

import asyncio
import base64
import io
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
MAX_EXTRACTED_DOCUMENT_CHARS = 120_000

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

# These are the only upload namespaces that may ever be resolved back to local
# bytes for AI inference. Keeping this allow-list explicit preserves the SSRF
# and path-traversal boundary while allowing the three learning surfaces to
# share one attachment pipeline.
AI_MEDIA_FOLDERS = {"chat", "test-prep", "classroom"}

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
            detail="AI attachments must be uploaded through Lyo before sending.",
        )

    relative = path[len(_MEDIA_PREFIX):]
    pieces = relative.split("/")
    if len(pieces) != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment path")
    folder, filename = pieces
    if (
        not _FOLDER_RE.fullmatch(folder)
        or folder not in AI_MEDIA_FOLDERS
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


def _extract_document_content(
    data: bytes, mime_type: str
) -> tuple[str, List[Dict[str, Any]], int]:
    """Extract bounded text plus page provenance for source-aware answers.

    Gemini still receives the original file bytes.  Text extraction gives
    OpenAI a real document fallback, while page provenance lets either provider
    cite a source without inventing a page number.
    """
    if mime_type in {"text/plain", "text/markdown", "text/csv", "application/json"}:
        text = data.decode("utf-8", errors="replace").strip()
        return text[:MAX_EXTRACTED_DOCUMENT_CHARS], [], 0

    if mime_type != "application/pdf":
        return "", [], 0

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages: List[Dict[str, Any]] = []
        rendered: List[str] = []
        remaining = MAX_EXTRACTED_DOCUMENT_CHARS
        for index, page in enumerate(reader.pages, 1):
            if remaining <= 0:
                break
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                pages.append({"page": index, "has_text": False})
                continue
            bounded = page_text[:remaining]
            pages.append(
                {
                    "page": index,
                    "has_text": True,
                    "excerpt": bounded[:700],
                }
            )
            rendered.append(f"[Page {index}]\n{bounded}")
            remaining -= len(bounded)

        return "\n\n".join(rendered).strip(), pages, len(reader.pages)
    except Exception:
        # A scanned/image-only PDF can still be handled by a native
        # multimodal provider such as Gemini. Do not reject it here.
        return "", [], 0


def _extract_document_text(data: bytes, mime_type: str) -> str:
    """Compatibility wrapper retained for tests/callers that only need text."""
    return _extract_document_content(data, mime_type)[0]


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
    """Recover the latest attachment-bearing Chat turn for follow-up questions."""
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
            # Conversation history only owns the Chat namespace. Test Prep and
            # Classroom references are supplied explicitly by those workflows.
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
    """Return provider-neutral inline-data parts after validating attachments."""
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
                detail=f"Unsupported AI attachment type '{mime_type}'.",
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
                detail="Each AI attachment must be 10MB or smaller.",
            )
        total_size += stat.st_size
        if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="AI attachments may total at most 20MB per message.",
            )

        data = await asyncio.to_thread(path.read_bytes)
        part: Dict[str, Any] = {
            "type": "media_base64",
            "mime_type": mime_type,
            "data": base64.b64encode(data).decode("ascii"),
            "name": _clean_label(item.name or path.name),
        }
        if not mime_type.startswith("image/"):
            extracted_text, source_pages, page_count = await asyncio.to_thread(
                _extract_document_content, data, mime_type
            )
            if extracted_text:
                part["extracted_text"] = extracted_text
            if source_pages:
                part["source_pages"] = source_pages
            if page_count:
                part["page_count"] = page_count
        prepared.append(part)
    return prepared
