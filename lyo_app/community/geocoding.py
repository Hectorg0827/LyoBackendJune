"""Place lookup for Community search and event addresses.

Uses an OpenStreetMap geocoder (Photon by default, configurable with
``COMMUNITY_GEOCODER_URL``; set it empty to disable). Provider failures return
no places — search then falls back to a topic search instead of an error.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any, Optional

import httpx

from lyo_app.community.schemas import PlaceSuggestion

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://photon.komoot.io/api/"
_CACHE_TTL_SECONDS = 3600
_CACHE_MAX_ENTRIES = 512
_cache: dict[tuple, tuple[float, list[PlaceSuggestion]]] = {}

# Area types that make sense as "move the map here" destinations.
AREA_KINDS = frozenset(
    {"city", "town", "village", "district", "borough", "suburb", "locality",
     "neighbourhood", "county", "state", "postcode", "region"}
)

_DEFAULT_RADIUS_KM = {
    "country": 50.0,
    "state": 50.0,
    "region": 40.0,
    "county": 25.0,
    "city": 15.0,
    "town": 8.0,
    "borough": 8.0,
    "district": 6.0,
    "suburb": 4.0,
    "village": 4.0,
    "locality": 4.0,
    "neighbourhood": 3.0,
    "postcode": 4.0,
}


def _clean(value: Any, max_length: int = 200) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] or None


def _radius_from_extent(extent: Any, fallback: float) -> float:
    try:
        min_lon, max_lat, max_lon, min_lat = (float(value) for value in extent)
    except (TypeError, ValueError):
        return fallback
    center_lat = (max_lat + min_lat) / 2
    height_km = abs(max_lat - min_lat) * 111.0
    width_km = abs(max_lon - min_lon) * 111.0 * max(math.cos(math.radians(center_lat)), 0.15)
    half_diagonal = math.hypot(height_km, width_km) / 2
    return max(1.5, min(half_diagonal, 50.0))


def _kind(properties: dict) -> str:
    kind = (properties.get("type") or "").lower()
    value = (properties.get("osm_value") or "").lower()
    if properties.get("postcode") and not properties.get("name"):
        return "postcode"
    if value in AREA_KINDS:
        return value
    if kind == "house":
        return "address"
    if kind in {"street"}:
        return "street"
    if kind in AREA_KINDS or kind in {"other"}:
        return kind if kind != "other" else "venue"
    return kind or "venue"


def _label(properties: dict) -> str:
    street = " ".join(
        str(value)
        for value in [properties.get("housenumber"), properties.get("street")]
        if value
    )
    parts = [
        properties.get("name") or street or properties.get("postcode"),
        street if properties.get("name") and street else None,
        properties.get("district") if properties.get("district") != properties.get("name") else None,
        properties.get("city") if properties.get("city") != properties.get("name") else None,
        properties.get("state"),
        properties.get("postcode") if properties.get("name") else None,
    ]
    seen: list[str] = []
    for part in parts:
        text = _clean(part)
        if text and text not in seen:
            seen.append(text)
    return ", ".join(seen)[:300]


def parse_photon(payload: Any) -> list[PlaceSuggestion]:
    """Convert a Photon GeoJSON response into place suggestions."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return []
    places: list[PlaceSuggestion] = []
    for feature in features:
        try:
            properties = feature.get("properties") or {}
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            kind = _kind(properties)
            name = _clean(properties.get("name") or properties.get("postcode") or properties.get("street"))
            if not name:
                continue
            fallback = _DEFAULT_RADIUS_KM.get(kind, 2.0)
            radius = _radius_from_extent(properties.get("extent"), fallback)
            places.append(
                PlaceSuggestion(
                    name=name,
                    label=_label(properties) or name,
                    kind=kind,
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=round(radius, 1),
                    is_area=kind in AREA_KINDS,
                )
            )
        except (AttributeError, IndexError, TypeError, ValueError) as exc:
            logger.debug("Skipping unusable geocoder feature: %s", exc)
    return places


async def geocode(
    query: str,
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    limit: int = 5,
) -> list[PlaceSuggestion]:
    text = " ".join((query or "").split())[:200]
    if len(text) < 2:
        return []
    endpoint = os.getenv("COMMUNITY_GEOCODER_URL", _DEFAULT_ENDPOINT)
    if not endpoint:
        return []

    bias = (
        (round(latitude, 1), round(longitude, 1))
        if latitude is not None and longitude is not None
        else None
    )
    cache_key = (text.lower(), bias, limit)
    cached = _cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return [place.model_copy() for place in cached[1]]

    params: dict[str, Any] = {"q": text, "limit": max(1, min(limit, 10)), "lang": "en"}
    if bias:
        params["lat"], params["lon"] = latitude, longitude
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            response = await client.get(
                endpoint,
                params=params,
                headers={"User-Agent": "LyoCommunity/1.0 (https://lyoai.app)"},
            )
            response.raise_for_status()
            places = parse_photon(response.json())
    except Exception as exc:  # Search degrades to a topic search.
        logger.warning("Community geocoder lookup failed: %s", exc)
        return []

    if len(_cache) >= _CACHE_MAX_ENTRIES:
        oldest = min(_cache, key=lambda key: _cache[key][0])
        _cache.pop(oldest, None)
    _cache[cache_key] = (time.monotonic(), places)
    return [place.model_copy() for place in places]
