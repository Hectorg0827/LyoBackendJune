"""The pre-launch feed check reads every page and flags clips that would not play."""
import importlib.util
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location(
    "serving_check", Path(__file__).resolve().parent.parent / "catalog" / "serving_check.py")
serving_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serving_check)


def clip(n, status="ready"):
    return {"id": n, "title": f"Clip {n}", "mediaStatus": status,
            "videoURL": f"https://api.example.test/v/{n}.mp4", "thumbnailURL": f"https://api.example.test/p/{n}.jpg"}


def handler(request):
    if request.url.path == "/api/v1/clips/discover":
        page = int(request.url.params["page"])
        clips = [clip(1), clip(2)] if page == 1 else [clip(3, status="missing")]
        return httpx.Response(200, json={"success": True, "clips": clips, "total": 3, "page": page, "perPage": 2})
    if request.url.path == "/p/2.jpg":
        return httpx.Response(404)
    return httpx.Response(200, headers={"content-length": "1234"})


def test_every_page_is_read_and_unplayable_clips_are_named():
    with httpx.Client(base_url="https://api.example.test", transport=httpx.MockTransport(handler)) as api:
        clips = serving_check.read_feed(api, {})
        problems = serving_check.check(api, clips)
    assert [c["id"] for c in clips] == [1, 2, 3]
    assert problems == ["Clip 2: poster HEAD 404", "Clip 3: mediaStatus 'missing'"]
