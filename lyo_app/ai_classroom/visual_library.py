"""Low-cost, rights-aware image discovery for Chat and live Classroom.

This does NOT synthesize facts or draw diagrams; deterministic visual blocks do
that. It returns one optional, sourced educational image with bounded network
work. Never proxy arbitrary model-provided URLs. Only server-chosen APIs are
called, and only known media/source domains are returned to mobile clients.
"""
from __future__ import annotations

import html
import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

# Exact domains, never suffix checks (to avoid e.g. nasa.gov.example.net).
_MEDIA_HOSTS = frozenset({
    "upload.wikimedia.org",
    "images.pexels.com",
    "images-assets.nasa.gov",
    "ids.si.edu",
})
_SOURCE_HOSTS = frozenset({
    "commons.wikimedia.org",
    "www.pexels.com",
    "images.nasa.gov",
    "www.si.edu",
})
_COMMERCIAL_LICENSES = frozenset({"cc0", "pdm", "by", "by-sa"})
_NASA_TOPICS = re.compile(
    r"\b(?:nasa|space|astronomy|apollo|galax(?:y|ies)|planet|solar system|"
    r"moon|mars|jupiter|saturn|nebula|telescope|astronaut|earth from space)\b", re.I,
)
_MUSEUM_TOPICS = re.compile(
    r"\b(?:museum|artifact|artefact|fossil|histor(?:y|ical)|ancient|"
    r"archaeolog|sculpture|paintings?|civilization|dinosaurs?)\b", re.I,
)
_PHOTO_TOPICS = re.compile(
    r"\b(?:photograph|photo|real image|real picture|actual|real[- ]world)\b", re.I,
)


def _allowed_https(url: str | None, hosts: frozenset[str]) -> bool:
    if not isinstance(url, str) or len(url) > 1200:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in hosts and bool(parsed.path)
    except ValueError:
        return False


def trusted_media_url(url: str | None) -> bool:
    return _allowed_https(url, _MEDIA_HOSTS)


def trusted_source_url(url: str | None) -> bool:
    return _allowed_https(url, _SOURCE_HOSTS)


def _plain(value: Any, max_length: int = 220) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())[:max_length]


def commercial_commons_license(name: str) -> bool:
    """Only licenses safe for commercial reuse, with no modification required."""
    value = _plain(name).casefold().replace("_", "-")
    if not value or re.search(r"\b(?:nc|nd|noncommercial|non-commercial|no derivatives)\b", value):
        return False
    return bool(
        re.search(r"\bcc\s*(?:by(?:-sa)?|zero|0)\b", value)
        or re.search(r"\b(?:public domain|public-domain|pd|pdm|cc0)\b", value)
    )


@dataclass(frozen=True)
class LibraryImage:
    url: str
    source_url: str
    attribution: str
    provider: str

    def __post_init__(self) -> None:
        if not trusted_media_url(self.url) or not trusted_source_url(self.source_url):
            raise ValueError("Image and source must use approved HTTPS hosts")
        if not self.attribution:
            raise ValueError("Images require a visible attribution/license label")


def nasa_image(payload: dict[str, Any]) -> LibraryImage | None:
    for entry in (payload.get("collection") or {}).get("items") or []:
        try:
            data = (entry.get("data") or [])[0]
            nasa_id = str(data.get("nasa_id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{3,90}", nasa_id):
                continue
            # NASA archives can contain third-party copyrighted submissions.
            description = str(data.get("description") or "")[:1200].casefold()
            if any(term in description for term in ("copyright ", "©", "all rights reserved")):
                continue
            links = entry.get("links") or []
            url = next(
                (link.get("href") for link in links
                 if trusted_media_url(link.get("href"))
                 and str(link.get("render") or "image").lower() == "image"),
                None,
            )
            if url:
                return LibraryImage(
                    url=url,
                    source_url="https://images.nasa.gov/details/" + quote(nasa_id),
                    attribution="NASA Image Library · Usage subject to NASA media guidelines",
                    provider="nasa",
                )
        except (ValueError, TypeError, IndexError, AttributeError):
            continue
    return None


def smithsonian_image(payload: dict[str, Any]) -> LibraryImage | None:
    for record in (payload.get("response") or {}).get("rows") or []:
        try:
            content = record.get("content") or {}
            media = (((content.get("descriptiveNonRepeating") or {})
                      .get("online_media") or {}).get("media") or [])
            record_id = str(record.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,110}", record_id):
                continue
            for item in media:
                usage = (item.get("usage") or {}).get("access")
                if str(usage).upper() != "CC0":
                    continue
                url = item.get("thumbnail") or item.get("content")
                if trusted_media_url(url):
                    return LibraryImage(
                        url=url,
                        source_url="https://www.si.edu/object/" + quote(record_id, safe=""),
                        attribution="Smithsonian Open Access · CC0",
                        provider="smithsonian",
                    )
        except (ValueError, TypeError, AttributeError):
            continue
    return None


def pexels_image(payload: dict[str, Any]) -> LibraryImage | None:
    for photo in payload.get("photos") or []:
        try:
            src = photo.get("src") or {}
            url = src.get("medium") or src.get("large")
            source = photo.get("url")
            creator = _plain(photo.get("photographer") or "Pexels contributor", 90)
            if trusted_media_url(url) and trusted_source_url(source):
                return LibraryImage(
                    url=url, source_url=source,
                    attribution=f"Photo by {creator} on Pexels · Pexels License",
                    provider="pexels",
                )
        except (ValueError, TypeError, AttributeError):
            continue
    return None


def openverse_image(payload: dict[str, Any]) -> LibraryImage | None:
    """Openverse indexes external works; re-check licensing and hosted domains."""
    for result in payload.get("results") or []:
        try:
            license_name = str(result.get("license") or "").lower()
            if license_name not in _COMMERCIAL_LICENSES:
                continue
            url = result.get("url")
            source = result.get("foreign_landing_url")
            # Initial rollout permits only Wikimedia-hosted Openverse results.
            # It must not become a generic third-party image URL pass-through.
            if not (trusted_media_url(url) and urlparse(url).hostname == "upload.wikimedia.org"
                    and trusted_source_url(source)
                    and urlparse(source).hostname == "commons.wikimedia.org"):
                continue
            creator = _plain(result.get("creator") or "Unknown creator", 90)
            return LibraryImage(
                url=url, source_url=source,
                attribution=f"{creator} · {license_name.upper()} · via Openverse",
                provider="openverse",
            )
        except (ValueError, TypeError, AttributeError):
            continue
    return None


async def _lookup(client: httpx.AsyncClient, provider: str, query: str) -> LibraryImage | None:
    """One bounded public API request. Credentials are server-side only."""
    try:
        if provider == "nasa":
            response = await client.get(
                "https://images-api.nasa.gov/search",
                params={"q": query, "media_type": "image", "page_size": 6},
            )
            parse = nasa_image
        elif provider == "smithsonian":
            key = os.getenv("SMITHSONIAN_API_KEY", "").strip()
            if not key:
                return None
            response = await client.get(
                "https://api.si.edu/openaccess/api/v1.0/search",
                params={"q": query, "api_key": key, "rows": 6, "start": 0},
            )
            parse = smithsonian_image
        elif provider == "pexels":
            key = os.getenv("PEXELS_API_KEY", "").strip()
            if not key:
                return None
            response = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 6},
                headers={"Authorization": key},
            )
            parse = pexels_image
        elif provider == "openverse":
            response = await client.get(
                "https://api.openverse.org/v1/images/",
                params={
                    "q": query, "license": "cc0,pdm,by,by-sa",
                    "mature": "false", "page_size": 12,
                },
            )
            parse = openverse_image
        else:
            return None
        response.raise_for_status()
        return parse(response.json())
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        logger.debug("Visual library %s lookup unavailable: %s", provider, type(exc).__name__)
        return None


def provider_order(query: str, *, phase: str) -> tuple[str, ...]:
    """Specialists before Commons for matching content; general fallback after."""
    if phase == "priority":
        if _NASA_TOPICS.search(query):
            return ("nasa",)
        if _MUSEUM_TOPICS.search(query) and os.getenv("SMITHSONIAN_API_KEY"):
            return ("smithsonian",)
        if _PHOTO_TOPICS.search(query) and os.getenv("PEXELS_API_KEY"):
            return ("pexels",)
        return ()
    return ("openverse", "pexels", "smithsonian", "nasa")


async def find_library_image(query: str, *, phase: str = "fallback") -> LibraryImage | None:
    """Return at most one verified result; never fail the lesson or store secrets."""
    q = " ".join((query or "").split())[:140]
    if len(q) < 3:
        return None
    providers = provider_order(q, phase=phase)
    if not providers:
        return None
    async with httpx.AsyncClient(
        timeout=1.2, follow_redirects=False,
        headers={"User-Agent": "LyoAI/1.0 (https://lyoai.app; educational image lookup)"},
    ) as client:
        for provider in providers:
            # Key-requiring providers return immediately if not configured.
            found = await _lookup(client, provider, q)
            if found:
                return found
    return None
