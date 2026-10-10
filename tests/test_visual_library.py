"""Visual library licensing, parsing and provider-routing regressions."""
from __future__ import annotations

import pytest

from lyo_app.ai_classroom import visual_library as lib


def test_license_gate_denies_noncommercial_derivative_or_unknown():
    for license_name in ("CC BY", "CC BY-SA 4.0", "CC0 1.0", "Public domain"):
        assert lib.commercial_commons_license(license_name)
    for license_name in ("CC BY-NC-SA 4.0", "CC BY-ND 4.0", "", "All rights reserved"):
        assert not lib.commercial_commons_license(license_name)


def test_strict_hosts_block_tracker_subdomains_http_and_javascript():
    assert lib.trusted_media_url("https://upload.wikimedia.org/example.jpg")
    assert lib.trusted_media_url("https://images.pexels.com/photos/1/a.jpeg")
    assert lib.trusted_media_url("https://images-assets.nasa.gov/image/test.jpg")
    assert lib.trusted_media_url("https://ids.si.edu/ids/deliveryService?id=abc")
    assert lib.trusted_source_url("https://www.si.edu/object/edanmdm-x")
    assert not lib.trusted_media_url("https://images.pexels.com.evil.test/a.jpeg")
    assert not lib.trusted_media_url("http://upload.wikimedia.org/a.jpg")
    assert not lib.trusted_source_url("javascript:alert(1)")
    assert not lib.trusted_source_url("https://evil.test/landing")


def test_openverse_accepts_only_commercial_licenses_and_known_commons_files():
    base = {
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/leaf.jpg",
        "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Leaf.jpg",
        "creator": "Scientist", "license": "by-sa",
    }
    result = lib.openverse_image({"results": [base]})
    assert result is not None
    assert result.provider == "openverse"
    assert "BY-SA" in result.attribution
    assert lib.openverse_image({"results": [{**base, "license": "by-nc"}]}) is None
    assert lib.openverse_image({"results": [{**base, "url": "https://tracker.test/a.jpg"}]}) is None
    assert lib.openverse_image({"results": [{**base, "foreign_landing_url": "https://unsafe.test/"}]}) is None
    assert lib.openverse_image({"results": [{**base, "license": "unknown"}]}) is None


def test_nasa_search_parses_primary_media_and_keeps_attributed_source():
    record = {"collection": {"items": [{
        "data": [{"nasa_id": "PIA00001", "description": "NASA Mars rover photo"}],
        "links": [{"href": "https://images-assets.nasa.gov/image/PIA00001/PIA00001~thumb.jpg",
                   "render": "image"}],
    }]}}
    found = lib.nasa_image(record)
    assert found.provider == "nasa"
    assert found.source_url == "https://images.nasa.gov/details/PIA00001"
    assert "NASA" in found.attribution
    record["collection"]["items"][0]["data"][0]["description"] = "Copyright Example Labs"
    assert lib.nasa_image(record) is None


def test_smithsonian_accepts_only_cc0_media():
    record = {"response": {"rows": [{
        "id": "edanmdm-nmaahc_1",
        "content": {"descriptiveNonRepeating": {"online_media": {"media": [{
            "thumbnail": "https://ids.si.edu/ids/deliveryService?id=ABC",
            "usage": {"access": "CC0"},
        }]}}}
    }]}}
    found = lib.smithsonian_image(record)
    assert found is not None and found.provider == "smithsonian"
    assert found.source_url.startswith("https://www.si.edu/object/")
    assert "CC0" in found.attribution
    record["response"]["rows"][0]["content"]["descriptiveNonRepeating"]["online_media"]["media"][0]["usage"]["access"] = "Copyright"
    assert lib.smithsonian_image(record) is None


def test_pexels_reuses_api_photographer_credit_and_source():
    image = {"photos": [{
        "src": {"medium": "https://images.pexels.com/photos/123/leaf.jpeg"},
        "url": "https://www.pexels.com/photo/green-leaf-123/",
        "photographer": "Jane Artist",
    }]}
    found = lib.pexels_image(image)
    assert found is not None and found.provider == "pexels"
    assert "Jane Artist" in found.attribution
    image["photos"][0]["src"]["medium"] = "https://untrusted.test/leaf.jpeg"
    assert lib.pexels_image(image) is None


def test_specialist_routing_and_optional_keys(monkeypatch):
    monkeypatch.delenv("SMITHSONIAN_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert lib.provider_order("Mars rover landing", phase="priority") == ("nasa",)
    assert lib.provider_order("Ancient fossils", phase="priority") == ()
    assert lib.provider_order("leaf photograph", phase="priority") == ()
    assert lib.provider_order("plant photosynthesis", phase="priority") == ()
    monkeypatch.setenv("SMITHSONIAN_API_KEY", "fake")
    monkeypatch.setenv("PEXELS_API_KEY", "fake")
    assert lib.provider_order("Ancient fossils", phase="priority") == ("smithsonian",)
    assert lib.provider_order("leaf photograph", phase="priority") == ("pexels",)
    assert lib.provider_order("water cycle", phase="fallback")[0] == "openverse"


@pytest.mark.asyncio
async def test_lookup_gracefully_skips_api_keys_not_configured(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("SMITHSONIAN_API_KEY", raising=False)

    class NeverCalled:
        async def get(self, *args, **kwargs):
            raise AssertionError("must not send optional requests with no key")

    assert await lib._lookup(NeverCalled(), "pexels", "leaf") is None
    assert await lib._lookup(NeverCalled(), "smithsonian", "history") is None


@pytest.mark.asyncio
async def test_lookup_handles_rate_limit_without_disclosing_credentials(monkeypatch):
    class RateLimitedClient:
        async def get(self, *args, **kwargs):
            raise lib.httpx.HTTPStatusError(
                "429 rate limited", request=lib.httpx.Request("GET", "https://api.openverse.org/v1/images/"),
                response=lib.httpx.Response(429),
            )

    assert await lib._lookup(RateLimitedClient(), "openverse", "biology") is None


@pytest.mark.asyncio
async def test_library_fallback_stops_after_first_verified_media(monkeypatch):
    seen = []

    async def fake_lookup(client, provider, query):
        seen.append(provider)
        if provider == "pexels":
            return lib.LibraryImage(
                url="https://images.pexels.com/photos/2/b.jpg",
                source_url="https://www.pexels.com/photo/b-2/",
                attribution="Photo by Artist on Pexels · Pexels License",
                provider="pexels",
            )
        return None

    monkeypatch.setattr(lib, "_lookup", fake_lookup)
    # No actual network needed: AsyncClient constructor has no HTTP activity.
    result = await lib.find_library_image("real leaf", phase="fallback")
    assert result and result.provider == "pexels"
    assert seen == ["openverse", "pexels"]


def test_model_supplied_untrusted_images_remain_rejected():
    from pydantic import ValidationError
    from lyo_app.ai_classroom.teaching_visuals import TeachingVisual
    attrs = dict(
        kind="annotated_image",
        title="Biology diagram",
        caption="Observe the real physical features.",
        description="A photograph showing plant leaf structures.",
        image_query="leaf",
    )
    with pytest.raises(ValidationError):
        TeachingVisual(**attrs, image_url="https://attacker.test/a.jpg")
    with pytest.raises(ValidationError):
        TeachingVisual(**attrs, source_url="https://attacker.test/post")
    TeachingVisual(
        **attrs,
        image_url="https://images.pexels.com/photos/2/b.jpg",
        source_url="https://www.pexels.com/photo/b-2/",
    )
