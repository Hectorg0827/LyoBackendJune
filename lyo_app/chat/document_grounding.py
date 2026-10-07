"""Document-grounding helpers for canonical Chat.

The model may write page-aware citations, but the server owns whether those
locations are valid. This module keeps attachment citations honest and exposes
page/navigation metadata without leaking extracted document text to clients.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Mapping

_PAGE_CITATION_RE = re.compile(r"【(?P<name>[^】]+?)\s+p\.\s*(?P<page>\d+)】")


def _canonical_name(item: Mapping[str, Any]) -> str:
    return str(item.get("name") or "Attachment").strip() or "Attachment"


def _available_pages(item: Mapping[str, Any]) -> List[int]:
    pages: List[int] = []
    for page in item.get("source_pages") or []:
        if not isinstance(page, Mapping):
            continue
        value = page.get("page")
        if isinstance(value, int) and value > 0:
            pages.append(value)
    return sorted(set(pages))


def source_descriptors(media_attachments: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return client-safe source metadata with page locations, never page text."""
    sources: List[Dict[str, Any]] = []
    for item in media_attachments or []:
        sources.append(
            {
                "name": _canonical_name(item),
                "mime_type": str(item.get("mime_type") or ""),
                "page_count": item.get("page_count"),
                "available_pages": _available_pages(item)[:100],
                "kind": str(item.get("source_kind") or "attachment"),
                "url": str(item.get("uri") or ""),
            }
        )
    return sources


def normalize_attachment_citations(
    text: str,
    media_attachments: Iterable[Mapping[str, Any]],
) -> str:
    """Downgrade invented attachment page citations to file-level citations.

    Valid page citations are preserved exactly. If a model cites a page that
    was not among the extracted pages for the named attachment, the server
    removes the invented page number instead of presenting false precision.
    """
    if not text:
        return text

    by_name: Dict[str, Dict[str, Any]] = {}
    for item in media_attachments or []:
        name = _canonical_name(item)
        record = {"name": name, "pages": set(_available_pages(item))}
        by_name[name.casefold()] = record
        by_name[os.path.basename(name).casefold()] = record

    if not by_name:
        return text

    def replace(match: re.Match[str]) -> str:
        raw_name = match.group("name").strip()
        page = int(match.group("page"))
        record = by_name.get(raw_name.casefold())
        if record is None:
            record = by_name.get(os.path.basename(raw_name).casefold())
        if record is None:
            # It may be a non-attachment citation style; leave it untouched.
            return match.group(0)
        pages = record["pages"]
        if page in pages:
            return f"【{record['name']} p. {page}】"
        return f"【{record['name']}】"

    return _PAGE_CITATION_RE.sub(replace, text)


def document_navigator_content(
    media_attachments: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build the cross-platform document navigator payload."""
    items: List[Dict[str, Any]] = []
    for descriptor in source_descriptors(media_attachments):
        pages = descriptor.get("available_pages") or []
        page_count = descriptor.get("page_count")
        detail_bits: List[str] = []
        if isinstance(page_count, int) and page_count > 0:
            detail_bits.append(f"{page_count} page" + ("s" if page_count != 1 else ""))
        if pages:
            if len(pages) <= 8:
                detail_bits.append("available: " + ", ".join(str(p) for p in pages))
            else:
                detail_bits.append(f"{len(pages)} extracted pages")

        items.append(
            {
                "label": descriptor["name"],
                "detail": " • ".join(detail_bits) or str(descriptor.get("mime_type") or "attachment"),
                "url": descriptor.get("url") or "",
                "page_count": page_count,
                "available_pages": pages,
            }
        )

    return {
        "title": "Document navigator",
        "items": items,
        "quick_actions": [
            "Summarize this document",
            "Show key dates",
            "Show key numbers",
            "Ask about a page",
        ],
    }


def attachment_grounding_prompt(
    media_attachments: Iterable[Mapping[str, Any]],
) -> str:
    """Create the model-facing page citation contract."""
    items = list(media_attachments or [])
    if not items:
        return ""

    lines = [
        "--- ATTACHMENT SOURCE GROUNDING ---",
        "When a factual claim comes from an attached document, cite its location inline.",
        "Use the exact form 【filename p. N】 only when extracted page N supports that claim.",
        "For images or documents without page-aware text, cite 【filename】.",
        "Never invent a page number or imply the attachment supports a claim it does not contain.",
    ]
    for item in items:
        name = _canonical_name(item)
        pages = _available_pages(item)
        page_count = item.get("page_count")
        if pages:
            lines.append(
                f"Source: {name} ({page_count or len(pages)} pages; extracted pages: "
                + ", ".join(str(page) for page in pages[:100])
                + ")"
            )
        else:
            lines.append(f"Source: {name} (native attachment; no extracted page text available)")
    lines.append("--- END ATTACHMENT SOURCE GROUNDING ---")
    return "\n".join(lines)
