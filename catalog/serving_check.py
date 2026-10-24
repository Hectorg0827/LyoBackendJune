"""Before Discover is switched on: read the feed as a signed-in user. Read-only.

Signs in with DISCOVER_CERTIFY_EMAIL and DISCOVER_CERTIFY_PASSWORD, reads every
page of /api/v1/clips/discover, and checks that each clip is ready and that
its video, and its poster when it has one, answer HEAD with a size from the
API's own host. Prints what the feed holds and exits 1 when it holds fewer
than --minimum clips or any check fails.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from discover_catalog import PatientTransport  # noqa: E402
from discover_media_certify import authenticate  # noqa: E402


def read_feed(api, auth):
    clips, page = [], 1
    while True:
        response = api.get("/api/v1/clips/discover", headers=auth,
                           params={"page": page, "per_page": 100, "sort": "latest"})
        response.raise_for_status()
        body = response.json()
        clips += body["clips"]
        if not body["clips"] or len(clips) >= body["total"]:
            return clips
        page += 1


def check(api, clips):
    # Only the API's own media is requested: feed URLs come from what learners
    # publish, and this check runs with the library account's secrets.
    api_host = api.base_url.host
    problems = []
    for clip in clips:
        title = clip.get("title") or f"clip {clip.get('id')}"
        if clip.get("mediaStatus") != "ready":
            problems.append(f"{title}: mediaStatus {clip.get('mediaStatus')!r}")
        for label, url in (("video", clip.get("videoURL")), ("poster", clip.get("thumbnailURL"))):
            if not url:
                # A learner's clip may have no poster; every clip needs a video.
                if label == "video":
                    problems.append(f"{title}: no video URL")
                continue
            if httpx.URL(url).host != api_host:
                problems.append(f"{title}: {label} is not on {api_host}")
                continue
            response = api.head(url, follow_redirects=False)
            if response.status_code != 200 or not int(response.headers.get("content-length") or 0):
                problems.append(f"{title}: {label} HEAD {response.status_code}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="https://api.lyoai.app")
    parser.add_argument("--minimum", type=int, default=37)
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.api, timeout=60, transport=PatientTransport(httpx.HTTPTransport())) as api:
        auth = {"Authorization": f"Bearer {authenticate(api)}"}
        clips = read_feed(api, auth)
        problems = check(api, clips)
    credited = sum(1 for clip in clips if (clip.get("attribution") or {}).get("credit"))
    subjects = Counter((clip.get("subject") or (clip.get("metadata") or {}).get("subject") or "?") for clip in clips)
    print(f"Discover feed: {len(clips)} clips, {credited} with a source credit")
    print("Subjects: " + ", ".join(f"{name} {count}" for name, count in subjects.most_common()))
    for problem in problems:
        print(f"PROBLEM {problem}")
    if len(clips) < args.minimum:
        print(f"PROBLEM only {len(clips)} clips; expected at least {args.minimum}")
    return 1 if problems or len(clips) < args.minimum else 0


if __name__ == "__main__":
    sys.exit(main())
