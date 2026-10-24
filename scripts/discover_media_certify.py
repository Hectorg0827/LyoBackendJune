"""Prove Discover media survives a redeploy, using the real API end to end.

The earlier verifier re-read one object it found already in the bucket, so it
never showed that a *new* upload lands in durable storage, and it never sent
a HEAD request. This one does both, in two phases around a redeploy:

  upload    makes a brand-new video and poster with ffmpeg, uploads them with
            POST /api/v1/media/upload as a real account, publishes them as a
            private clip, and checks GET, HEAD, valid 206 ranges and invalid
            416 ranges on the returned URLs. It also checks that publishing a
            missing or foreign video is refused. Writes a state file.

  reverify  run after redeploying the API. Reads the same URLs again and
            requires identical bytes, the same checks to pass, and responses
            from a process that did not serve the upload (X-Media-Instance),
            which is what proves the bytes outlived the old container. Many
            requests are sent so a second replica, if there is one, is seen.
            Then deletes the private test clip.

Authentication, one of:
  DISCOVER_CERTIFY_TOKEN                       a bearer token
  DISCOVER_CERTIFY_EMAIL, DISCOVER_CERTIFY_PASSWORD   logs in with /auth/login

Optional direct storage check (read-only credentials are enough):
  DISCOVER_CERTIFY_S3_ENDPOINT, DISCOVER_CERTIFY_S3_BUCKET,
  DISCOVER_CERTIFY_S3_ACCESS_KEY, DISCOVER_CERTIFY_S3_SECRET_KEY

  python scripts/discover_media_certify.py upload --api https://api.lyoai.app --state certify.json
  # redeploy the API, then:
  python scripts/discover_media_certify.py reverify --state certify.json

Exit status is 0 only when every check in the phase passed.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

INSTANCE_HEADER = "x-media-instance"


class Report:
    def __init__(self, phase, api):
        self.data = {"phase": phase, "api": api, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "cases": [], "instances": []}

    def check(self, name, passed, **evidence):
        self.data["cases"].append({"case": name, "passed": bool(passed), **evidence})
        return bool(passed)

    def saw(self, response):
        instance = response.headers.get(INSTANCE_HEADER)
        if instance and instance not in self.data["instances"]:
            self.data["instances"].append(instance)

    def finish(self, path=None, **extra):
        self.data.update(extra)
        self.data["passed"] = sum(c["passed"] for c in self.data["cases"])
        self.data["failed"] = len(self.data["cases"]) - self.data["passed"]
        self.data.setdefault("status", "passed" if self.data["failed"] == 0 else "failed")
        text = json.dumps(self.data, indent=2)
        if path:
            Path(path).write_text(text)
        print("DISCOVER_MEDIA_CERTIFICATION=" + json.dumps(self.data, separators=(",", ":")), flush=True)
        return self.data["status"] == "passed"


def make_fresh_media(folder):
    """A short H.264/AAC MP4 and a JPEG poster whose bytes have never existed before."""
    nonce = uuid.uuid4().hex
    video, poster = Path(folder) / f"certify-{nonce}.mp4", Path(folder) / f"certify-{nonce}.jpg"
    tone = 300 + int(nonce[:4], 16) % 600
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=4",
        "-f", "lavfi", "-i", f"sine=frequency={tone}:duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "30",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
        "-metadata", f"comment=lyo-discover-certify-{nonce}", str(video),
    ], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", str(video),
                    "-frames:v", "1", "-q:v", "3", str(poster)], check=True)
    return video, poster, nonce


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_media(client, report, label, url, expected, content_type):
    """GET, HEAD, valid ranges and invalid ranges against one media URL."""
    size = len(expected)
    full = client.get(url)
    report.saw(full)
    report.check(f"{label}_get_200_exact_bytes", full.status_code == 200 and full.content == expected,
                 http_status=full.status_code, bytes=len(full.content), sha256=sha256(full.content))
    report.check(f"{label}_get_content_type", full.headers.get("content-type", "").startswith(content_type),
                 content_type=full.headers.get("content-type"))
    report.check(f"{label}_get_accepts_ranges", full.headers.get("accept-ranges") == "bytes")

    head = client.head(url)
    report.saw(head)
    report.check(f"{label}_head_200_length_no_body", head.status_code == 200 and head.content == b""
                 and head.headers.get("content-length") == str(size)
                 and head.headers.get("accept-ranges") == "bytes",
                 http_status=head.status_code, content_length=head.headers.get("content-length"))

    middle = max(0, size // 2 - 512)
    for header, start, end in [
        ("bytes=0-1023", 0, min(1023, size - 1)),
        (f"bytes={middle}-{min(size - 1, middle + 1023)}", middle, min(size - 1, middle + 1023)),
        ("bytes=-1024", max(0, size - 1024), size - 1),
        (f"bytes={max(0, size - 2000)}-", max(0, size - 2000), size - 1),
    ]:
        response = client.get(url, headers={"Range": header})
        report.saw(response)
        report.check(f"{label}_range_{header}", response.status_code == 206
                     and response.content == expected[start:end + 1]
                     and response.headers.get("content-range") == f"bytes {start}-{end}/{size}",
                     http_status=response.status_code, content_range=response.headers.get("content-range"))

    ranged_head = client.head(url, headers={"Range": "bytes=0-1023"})
    report.saw(ranged_head)
    report.check(f"{label}_head_range_206", ranged_head.status_code == 206 and ranged_head.content == b""
                 and ranged_head.headers.get("content-range") == f"bytes 0-{min(1023, size - 1)}/{size}",
                 http_status=ranged_head.status_code, content_range=ranged_head.headers.get("content-range"))

    for method, header in [("GET", f"bytes={size}-"), ("GET", "bytes=999999999-"),
                           ("GET", "bytes=5-2"), ("GET", "bytes=0-1,4-5"), ("HEAD", f"bytes={size}-")]:
        response = client.request(method, url, headers={"Range": header})
        report.check(f"{label}_{method.lower()}_invalid_{header}_416",
                     response.status_code == 416 and response.headers.get("content-range") == f"bytes */{size}",
                     http_status=response.status_code, content_range=response.headers.get("content-range"))


def check_cloud_object(report, label, url, expected):
    """Read the object straight from the bucket, when credentials are given."""
    endpoint = os.getenv("DISCOVER_CERTIFY_S3_ENDPOINT")
    bucket = os.getenv("DISCOVER_CERTIFY_S3_BUCKET")
    if not (endpoint and bucket):
        report.data.setdefault("skipped", []).append(f"{label}_cloud_bytes (no storage credentials given)")
        return
    import boto3

    cloud = boto3.client("s3", endpoint_url=endpoint, region_name=os.getenv("DISCOVER_CERTIFY_S3_REGION", "auto"),
                         aws_access_key_id=os.getenv("DISCOVER_CERTIFY_S3_ACCESS_KEY"),
                         aws_secret_access_key=os.getenv("DISCOVER_CERTIFY_S3_SECRET_KEY"))
    path = urlsplit(url).path
    key = "media/" + path.split("/api/v1/media/file/", 1)[1]
    try:
        stored = cloud.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception as error:  # noqa: BLE001 - the report says what failed
        report.check(f"{label}_cloud_object_matches", False, key=key, error=type(error).__name__)
        return
    report.check(f"{label}_cloud_object_matches", stored == expected, key=key, sha256=sha256(stored))


def authenticate(client):
    token = os.getenv("DISCOVER_CERTIFY_TOKEN")
    if token:
        return token
    # A secret pasted with its line break is refused as a wrong password, and
    # neither an email address nor a typed password can end in one.
    email = (os.getenv("DISCOVER_CERTIFY_EMAIL") or "").strip()
    password = (os.getenv("DISCOVER_CERTIFY_PASSWORD") or "").strip("\r\n")
    if not (email and password):
        raise SystemExit("Set DISCOVER_CERTIFY_TOKEN, or DISCOVER_CERTIFY_EMAIL and DISCOVER_CERTIFY_PASSWORD")
    response = client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        # Say why, so a wrong password, a disabled account and a rate limit
        # are told apart; never echo the credentials.
        try:
            body = response.json()
            reason = body.get("detail") or (body.get("error") or {}).get("message") or body
        except ValueError:
            reason = response.text[:200]
        raise SystemExit(f"Sign-in at {client.base_url} was refused ({response.status_code}): {reason}. "
                         "The account must sign in on the website with this email and password; "
                         "an account made with Google or Apple sign-in has no password there.")
    return response.json()["access_token"]


def health(client):
    try:
        body = client.get("/health").json()
    except Exception:  # noqa: BLE001 - health is evidence, not a gate
        return {}
    return {"commit_sha": body.get("commit_sha"), "status": body.get("status")}


def upload(args):
    report = Report("upload", args.api)
    with httpx.Client(base_url=args.api, timeout=120, follow_redirects=False) as client:
        token = authenticate(client)
        auth = {"Authorization": f"Bearer {token}"}
        report.data["health"] = health(client)
        with tempfile.TemporaryDirectory() as folder:
            video_path, poster_path, nonce = make_fresh_media(folder)
            video, poster = video_path.read_bytes(), poster_path.read_bytes()
            urls = {}
            for label, folder_name, path, data, content_type in [
                ("video", "clips", video_path, video, "video/mp4"),
                ("poster", "clip_thumbnails", poster_path, poster, "image/jpeg"),
            ]:
                response = client.post("/api/v1/media/upload", headers=auth, data={"folder": folder_name},
                                       files={"file": (path.name, data, content_type)})
                body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                ok = report.check(f"{label}_upload_accepted", response.status_code == 200 and body.get("size") == len(data),
                                  http_status=response.status_code)
                if not ok:
                    report.finish(args.report, status="failed")
                    return False
                # Checks go through the API base the caller named, even if the
                # stored URL spells the host differently.
                urls[label] = {"stored": body["url"], "checked": args.api.rstrip("/") + body["path"]}
                check_media(client, report, label, urls[label]["checked"], data, content_type)
                check_cloud_object(report, label, urls[label]["checked"], data)

        publish = client.post("/api/v1/clips", headers=auth, json={
            "title": f"Discover certification {nonce[:8]}", "description": "Private release check; deleted after reverify.",
            "videoUrl": urls["video"]["stored"], "thumbnailUrl": urls["poster"]["stored"],
            "durationSeconds": 4, "subject": "Certification", "isPublic": False,
        })
        clip = publish.json().get("clip") or {}
        report.check("publish_private_clip_ready", publish.status_code == 200 and clip.get("mediaStatus") == "ready",
                     http_status=publish.status_code)
        missing = urls["video"]["stored"].rsplit("/", 1)[0] + f"/{uuid.uuid4().hex}.mp4"
        refused = client.post("/api/v1/clips", headers=auth, json={"title": "missing", "videoUrl": missing, "isPublic": False})
        report.check("publish_missing_upload_refused", refused.status_code == 422, http_status=refused.status_code)
        foreign = client.post("/api/v1/clips", headers=auth, json={"title": "foreign", "isPublic": False,
                                                                     "videoUrl": "https://example.com/video.mp4"})
        report.check("publish_foreign_video_refused", foreign.status_code == 400, http_status=foreign.status_code)

    state = {"api": args.api, "nonce": nonce, "urls": urls, "clip_id": clip.get("id"),
             "video_sha256": sha256(video), "video_bytes": len(video),
             "poster_sha256": sha256(poster), "poster_bytes": len(poster),
             "upload_instances": report.data["instances"], "upload_health": report.data["health"]}
    Path(args.state).write_text(json.dumps(state, indent=2))
    report.data["state_file"] = str(args.state)
    return report.finish(args.report)


def reverify(args):
    state = json.loads(Path(args.state).read_text())
    api = args.api or state["api"]
    report = Report("reverify", api)
    with httpx.Client(base_url=api, timeout=120, follow_redirects=False) as client:
        token = authenticate(client)
        auth = {"Authorization": f"Bearer {token}"}
        report.data["health"] = health(client)
        for label, content_type, digest in [("video", "video/mp4", state["video_sha256"]),
                                            ("poster", "image/jpeg", state["poster_sha256"])]:
            url = api.rstrip("/") + urlsplit(state["urls"][label]["checked"]).path
            body = client.get(url).content
            report.check(f"{label}_bytes_unchanged_after_redeploy", sha256(body) == digest,
                         sha256=sha256(body), expected=digest)
            check_media(client, report, label, url, body, content_type)
            check_cloud_object(report, label, url, body)
        # Many small reads, so a load balancer has the chance to reach every replica.
        for _ in range(args.probes):
            response = client.head(api.rstrip("/") + urlsplit(state["urls"]["video"]["checked"]).path,
                                   headers={"Range": "bytes=0-1"})
            report.saw(response)
        before, after = set(state["upload_instances"]), set(report.data["instances"])
        redeployed = bool(after) and not (after & before)
        report.check("served_by_a_process_that_did_not_serve_the_upload", redeployed,
                     upload_instances=sorted(before), reverify_instances=sorted(after))
        report.data["replicas_observed"] = len(after)
        if state.get("clip_id"):
            clip = client.get(f"/api/v1/clips/{state['clip_id']}", headers=auth)
            stored = (clip.json().get("clip") or {}) if clip.status_code == 200 else {}
            report.check("published_clip_unchanged", stored.get("videoURL") == state["urls"]["video"]["stored"]
                         and stored.get("mediaStatus") == "ready", http_status=clip.status_code)
            if not args.keep:
                deleted = client.delete(f"/api/v1/clips/{state['clip_id']}", headers=auth)
                report.check("private_test_clip_deleted", deleted.status_code == 200, http_status=deleted.status_code)
    return report.finish(args.report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="phase", required=True)
    up = sub.add_parser("upload")
    up.add_argument("--api", required=True)
    up.add_argument("--state", required=True)
    up.add_argument("--report")
    again = sub.add_parser("reverify")
    again.add_argument("--state", required=True)
    again.add_argument("--api", help="defaults to the API used for the upload")
    again.add_argument("--probes", type=int, default=30)
    again.add_argument("--keep", action="store_true", help="keep the private test clip")
    again.add_argument("--report")
    args = parser.parse_args(argv)
    ok = upload(args) if args.phase == "upload" else reverify(args)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
