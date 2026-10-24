"""Build Discover's STEM library from openly licensed videos, with their credit.

Discover needs real, playable, rights-cleared STEM videos. This tool never
invents a library entry: every item comes from a source's own API, a person
approves it, and nothing is published until its bytes have been downloaded,
encoded for phones, uploaded to durable storage and played back over HTTP.

  search    Query NASA's Image and Video Library (public domain) or Wikimedia
            Commons (Creative Commons) and print draft manifest entries with
            the licence each source reports. Drafts are not approved.

  validate  Check a manifest offline: every approved entry has an allowed
            licence, a source link and credit, a reviewer, and a subject; at
            least --minimum entries are approved; which STEM areas are covered.

  ingest    For each approved entry: download from the source host, refuse
            anything unplayable or too short, trim and encode an H.264/AAC MP4
            with its index at the front (so playback starts before the
            download ends), cut a poster, upload both through the real API,
            publish the clip with its source, licence and credit, and check
            GET, HEAD, 206 and 416 on the result. A ledger makes reruns safe.

Licences: public domain, CC0, CC BY and CC BY-SA only. NonCommercial and
NoDerivatives licences are refused (Lyo is a commercial product, and trimming
and re-encoding is adapting). Material NASA did not make itself must be
cleared by the reviewer; the search flags descriptions that mention it.
NASA drafts, and public domain Commons drafts, are published silent
(clip.audio "mute"): the footage is public domain, but the library music in
many government videos is licensed to the agency alone. A reviewer who hears
only narration or natural sound sets "keep".

  python scripts/discover_catalog.py search nasa "Perseverance landing" >> drafts.jsonl
  python scripts/discover_catalog.py search commons "mitosis" >> drafts.jsonl
  # edit: pick entries into catalog.json, set subject, review.approved etc.
  python scripts/discover_catalog.py validate --manifest catalog.json
  DISCOVER_CERTIFY_EMAIL=... DISCOVER_CERTIFY_PASSWORD=... \\
    python scripts/discover_catalog.py ingest --manifest catalog.json --api https://api.lyoai.app

The account used for ingest becomes the clips' publisher; use a dedicated
"Lyo Library" account rather than a person's.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discover_media_certify import Report, authenticate, check_media, sha256  # noqa: E402

USER_AGENT = "LyoDiscoverCatalog/1.0 (https://lyoai.app; library ingestion)"
SOURCE_HOSTS = {"images-assets.nasa.gov", "images-api.nasa.gov", "upload.wikimedia.org"}
STEM_AREAS = ["science", "math", "engineering", "technology", "coding", "astronomy", "biology",
              "chemistry", "physics", "robotics", "environment"]
LEVELS = {"beginner", "intermediate", "advanced"}
# A source only has to fit on the runner's disk; a two-minute fractal zoom,
# all detail, is over 600 MB.
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
MIN_SECONDS, MAX_SECONDS = 5, 90
# The API refuses any request over 10 MB (lyo_app/auth/security_middleware.py)
# before the upload route's own limits apply; leave room for the multipart
# envelope around the file.
MAX_UPLOAD_BYTES = int(9.5 * 1024 * 1024)
AUDIO_KBPS = 128
NASA_GUIDELINES = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
THIRD_PARTY_HINTS = re.compile(r"copyright|©|courtesy of|used with permission|all rights reserved"
                               r"|music (provided|licensed|courtesy)|production music|universal music", re.I)
AUDIO_CHOICES = {"keep", "mute"}


# ── Licences ────────────────────────────────────────────────────────────────

def licence_family(name):
    """'public-domain', 'cc0', 'cc-by', 'cc-by-sa', or None when not allowed."""
    value = (name or "").strip().lower().replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    if not value:
        return None
    if "nc" in value.split() or "noncommercial" in value or "nd" in value.split() or "noderiv" in value:
        return None
    if value.startswith(("public domain", "pd ")) and "cc" not in value.split():
        return "public-domain"
    if value.startswith("cc0") or value.startswith("cc zero"):
        return "cc0"
    if value.startswith("cc by sa"):
        return "cc-by-sa"
    if value.startswith("cc by"):
        return "cc-by"
    return None


def attribution_line(source):
    """The visible credit, e.g. 'NASA/JPL-Caltech · Public domain'."""
    credit = (source.get("credit") or "").strip()
    licence = (source.get("license") or "").strip()
    return " · ".join(part for part in [credit, licence] if part)[:300]


# ── Searching sources ───────────────────────────────────────────────────────

def _strip_html(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def nasa_entries(search_body, collections):
    """Draft entries from an images-api.nasa.gov search and its asset lists."""
    entries = []
    for item in search_body.get("collection", {}).get("items", []):
        data = (item.get("data") or [{}])[0]
        nasa_id = data.get("nasa_id")
        if data.get("media_type") != "video" or not nasa_id:
            continue
        assets = [a.replace("http://", "https://", 1) for a in collections.get(item.get("href"), [])]
        mp4s = [a for a in assets if a.lower().endswith(".mp4")]
        preferred = next((a for suffix in ("~medium.mp4", "~small.mp4", "~orig.mp4", "~large.mp4")
                          for a in mp4s if a.endswith(suffix)), mp4s[0] if mp4s else None)
        if not preferred:
            continue
        center = data.get("center") or ""
        # secondary_creator names the video's producer, or sometimes its
        # music licensor; neither is the credit NASA asks for.
        credit = "NASA/JPL-Caltech" if center == "JPL" else f"NASA/{center}" if center else "NASA"
        description = _strip_html(data.get("description") or data.get("description_508"))
        provenance = " ".join([description or "", data.get("secondary_creator") or "", data.get("photographer") or ""])
        entries.append(draft(
            f"nasa-{nasa_id}", data.get("title") or nasa_id, description,
            source={"name": "NASA Image and Video Library",
                    "pageUrl": f"https://images.nasa.gov/details/{quote(nasa_id)}",
                    "mediaUrl": preferred, "license": "Public domain", "licenseUrl": NASA_GUIDELINES,
                    "credit": credit},
            tags=[k for k in (data.get("keywords") or [])][:8],
            rights_check=bool(THIRD_PARTY_HINTS.search(provenance)),
            # NASA's footage is public domain; the library music many of its
            # videos carry is licensed to NASA, not to us. A reviewer who hears
            # only narration or natural sound can set "keep".
            audio="mute",
        ))
    return entries


def commons_entries(body):
    """Draft entries from a Commons API query with imageinfo and extmetadata."""
    entries = []
    pages = body.get("query", {}).get("pages", [])
    pages = pages.values() if isinstance(pages, dict) else pages
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        value = lambda key: _strip_html((meta.get(key) or {}).get("value"))
        if not (info.get("mime") or "").startswith("video/") or not info.get("url"):
            continue
        licence = value("LicenseShortName")
        title = re.sub(r"^File:", "", page.get("title") or "")
        title = re.sub(r"\.(webm|ogv|ogg|mp4|mpg|mpeg)$", "", title, flags=re.I).replace("_", " ")
        entries.append(draft(
            f"commons-{page.get('pageid')}", title, value("ImageDescription")[:600],
            source={"name": "Wikimedia Commons", "pageUrl": info.get("descriptionurl"),
                    "mediaUrl": info.get("url"), "license": licence, "licenseUrl": value("LicenseUrl") or None,
                    "credit": value("Artist") or value("Credit")},
            tags=[],
            rights_check=licence_family(licence) is None,
            # A CC licence covers the whole file, soundtrack included. Public
            # domain uploads are mostly US government videos, whose music is
            # often licensed like NASA's.
            audio="mute" if licence_family(licence) == "public-domain" else "keep",
        ))
    return entries


def draft(entry_id, title, description, source, tags, rights_check, audio="keep"):
    return {
        "id": entry_id, "title": (title or "")[:200], "description": description or "",
        "subject": None, "topic": None, "level": "beginner", "tags": tags, "keyPoints": [],
        "source": source, "clip": {"start": 0, "duration": None, "audio": audio},
        "review": {"approved": False, "reviewer": None, "factChecked": False, "ageAppropriate": False,
                   "rightsCleared": not rights_check, "notes": ""},
    }


def search(args):
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=60, headers=headers, follow_redirects=True) as client:
        if args.source == "nasa":
            body = client.get("https://images-api.nasa.gov/search",
                              params={"q": args.query, "media_type": "video", "page_size": args.limit}).json()
            collections = {}
            for item in body.get("collection", {}).get("items", [])[: args.limit]:
                href = item.get("href")
                if href and urlsplit(href).hostname in SOURCE_HOSTS:
                    collections[href] = client.get(href).json()
            entries = nasa_entries(body, collections)
        else:
            body = client.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "formatversion": "2", "generator": "search",
                "gsrnamespace": "6", "gsrsearch": f"{args.query} filetype:video", "gsrlimit": args.limit,
                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription",
            }).json()
            entries = commons_entries(body)
    for entry in entries[: args.limit]:
        print(json.dumps(entry, ensure_ascii=False))
    return 0


# ── Validating a manifest ───────────────────────────────────────────────────

def entry_problems(entry):
    problems = []
    source = entry.get("source") or {}
    review = entry.get("review") or {}
    if not licence_family(source.get("license")):
        problems.append(f"licence not allowed: {source.get('license')!r}")
    if not (source.get("pageUrl") or "").startswith("https://"):
        problems.append("missing https source page")
    if urlsplit(source.get("mediaUrl") or "").hostname not in SOURCE_HOSTS:
        problems.append("media must come from a recognised source host")
    if not (source.get("credit") or "").strip():
        problems.append("missing credit")
    if not (entry.get("title") or "").strip():
        problems.append("missing title")
    if not (entry.get("subject") or "").strip():
        problems.append("missing subject")
    if entry.get("level") not in LEVELS:
        problems.append("level must be beginner, intermediate or advanced")
    for flag in ("factChecked", "ageAppropriate", "rightsCleared"):
        if review.get(flag) is not True:
            problems.append(f"review.{flag} is not confirmed")
    if not (review.get("reviewer") or "").strip():
        problems.append("review.reviewer is not named")
    if (entry.get("clip") or {}).get("audio", "keep") not in AUDIO_CHOICES:
        problems.append("clip.audio must be keep or mute")
    return problems


def validate_manifest(entries, minimum):
    approved = [e for e in entries if (e.get("review") or {}).get("approved") is True]
    problems = {e.get("id"): entry_problems(e) for e in approved}
    problems = {k: v for k, v in problems.items() if v}
    ids = [e.get("id") for e in entries]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    covered = sorted({area for e in approved if not entry_problems(e)
                      for area in STEM_AREAS
                      if area in " ".join([e.get("subject") or "", e.get("topic") or "", *e.get("tags", [])]).lower()})
    ready = len(approved) - len(problems)
    return {
        "entries": len(entries), "approved": len(approved), "ready": ready, "minimum": minimum,
        "problems": problems, "duplicate_ids": duplicates,
        "areas_covered": covered, "areas_missing": [a for a in STEM_AREAS if a not in covered],
        "status": "passed" if ready >= minimum and not problems and not duplicates else "failed",
    }


def load_manifest(path):
    data = json.loads(Path(path).read_text())
    return data["entries"] if isinstance(data, dict) else data


def validate(args):
    result = validate_manifest(load_manifest(args.manifest), args.minimum)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


# ── Encoding ────────────────────────────────────────────────────────────────

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                         check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(info.get("format", {}).get("duration") or (video or {}).get("duration") or 0)
    return {"video": video, "audio": audio, "duration": duration}


def index_at_front(path):
    """True when the MP4's moov box comes before mdat, so playback can start early."""
    with open(path, "rb") as handle:
        while True:
            header = handle.read(8)
            if len(header) < 8:
                return False
            size, kind = int.from_bytes(header[:4], "big"), header[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(handle.read(8), "big")
                handle.seek(size - 16, 1)
            elif size < 8:
                return False
            else:
                handle.seek(size - 8, 1)


def encode(source, out_video, out_poster, start, duration, mute=False, max_bytes=MAX_UPLOAD_BYTES):
    """Phone-friendly H.264 High/AAC MP4, index first, at most 1280px on the long edge.

    mute replaces the source's sound with silence, for footage whose soundtrack
    is not ours to republish. A clip that comes out larger than max_bytes is
    encoded again at the average bitrate that fits, so it can be uploaded.
    """
    info = probe(source)
    if mute:
        info["audio"] = None
    if not info["video"]:
        raise ValueError("no video stream")
    length = max(0.0, info["duration"] - start)
    take = min(length, duration or MAX_SECONDS, MAX_SECONDS)
    if take < MIN_SECONDS:
        raise ValueError(f"only {take:.1f}s of video; need at least {MIN_SECONDS}s")
    width, height = int(info["video"].get("width") or 0), int(info["video"].get("height") or 0)
    if min(width, height) < 360:
        raise ValueError(f"resolution {width}x{height} is below 360p")
    def run(rate):
        command = ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start}", "-t", f"{take}", "-i", str(source)]
        if not info["audio"]:
            # A silent track keeps every clip the same shape for players.
            command += ["-f", "lavfi", "-t", f"{take}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        command += [
            "-map", "0:v:0", "-map", "0:a:0" if info["audio"] else "1:a:0",
            "-vf", "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=fps='min(30,source_fps)'",
            "-c:v", "libx264", "-preset", "slow", *rate, "-profile:v", "high", "-level:v", "4.0",
            "-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ac", "2", "-ar", "44100",
            "-movflags", "+faststart", "-shortest", str(out_video),
        ]
        subprocess.run(command, check=True)

    run(["-crf", "23"])
    if max_bytes and out_video.stat().st_size > max_bytes:
        # 10% under the average that fits, and a cap on peaks, so the file lands
        # inside the limit instead of near it.
        video_kbps = int(max_bytes * 8 / 1000 / take * 0.9) - AUDIO_KBPS
        if video_kbps < 300:
            raise ValueError(f"{take:.0f}s cannot fit in {max_bytes // 1024} KB at a watchable bitrate")
        run(["-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.2)}k", "-bufsize", f"{video_kbps * 2}k"])
        if out_video.stat().st_size > max_bytes:
            raise ValueError(f"encoded clip is {out_video.stat().st_size // 1024} KB, over the {max_bytes // 1024} KB upload limit")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{min(1.0, take / 3):.2f}", "-i", str(out_video),
                    "-frames:v", "1", "-q:v", "3", str(out_poster)], check=True)
    result = probe(out_video)
    if (result["video"] or {}).get("codec_name") != "h264" or (result["audio"] or {}).get("codec_name") != "aac":
        raise ValueError("encoded file is not H.264/AAC")
    if not index_at_front(out_video):
        raise ValueError("encoded MP4 does not start with its index")
    return round(result["duration"], 2)


# ── Ingesting ───────────────────────────────────────────────────────────────

class PatientTransport(httpx.BaseTransport):
    """Waits and asks again when the API's rate limiter answers 429.

    The API allows 120 requests a minute from one address, and checking one
    clip (GET, HEAD, three ranges, four 416s, for video and poster) is a burst
    of two dozen. A 429 comes from the limiter before the request is handled,
    so asking again cannot publish anything twice.
    """

    def __init__(self, inner, waits=(15, 30, 60), sleep=time.sleep):
        self.inner, self.waits, self.sleep = inner, waits, sleep

    def handle_request(self, request):
        for wait in self.waits:
            response = self.inner.handle_request(request)
            if response.status_code != 429:
                return response
            response.close()
            self.sleep(wait)
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


def download(client, url, destination):
    if urlsplit(url).hostname not in SOURCE_HOSTS:
        raise ValueError(f"refusing to download from {urlsplit(url).hostname}")
    size = 0
    with client.stream("GET", url) as response:
        response.raise_for_status()
        final_host = urlsplit(str(response.url)).hostname
        if final_host not in SOURCE_HOSTS:
            raise ValueError(f"source redirected to {final_host}")
        with open(destination, "wb") as handle:
            for chunk in response.iter_bytes(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("source file is larger than the download limit")
                handle.write(chunk)
    return size


def ingest_entry(api, auth, sources, entry, report, workdir):
    source = entry["source"]
    raw, video, poster = workdir / "source", workdir / "clip.mp4", workdir / "poster.jpg"
    download(sources, source["mediaUrl"], raw)
    window = entry.get("clip") or {}
    duration = encode(raw, video, poster, float(window.get("start") or 0), window.get("duration"),
                      mute=window.get("audio") == "mute")
    uploaded = {}
    for label, folder, path, content_type in [("video", "clips", video, "video/mp4"),
                                              ("poster", "clip_thumbnails", poster, "image/jpeg")]:
        data = path.read_bytes()
        response = api.post("/api/v1/media/upload", headers=auth, data={"folder": folder},
                            files={"file": (path.name, data, content_type)})
        response.raise_for_status()
        uploaded[label] = response.json()
        check_media(api, report, f"{entry['id']}_{label}", str(api.base_url).rstrip("/") + uploaded[label]["path"],
                    data, content_type)
    body = {
        "title": entry["title"], "description": entry.get("description") or None,
        "videoUrl": uploaded["video"]["url"], "thumbnailUrl": uploaded["poster"]["url"],
        "durationSeconds": duration, "subject": entry["subject"], "topic": entry.get("topic"),
        "level": entry.get("level", "beginner"), "tags": entry.get("tags", []),
        "keyPoints": entry.get("keyPoints", []), "isPublic": True,
        "sourceName": source["name"], "sourceUrl": source["pageUrl"], "licenseName": source["license"],
        "licenseUrl": source.get("licenseUrl"), "attribution": attribution_line(source),
    }
    published = api.post("/api/v1/clips", headers=auth, json=body)
    if published.status_code == 409:
        clip_id = published.json()["error"]["details"]["clipId"]
        return {"clip_id": clip_id, "status": "already_published"}
    published.raise_for_status()
    clip = published.json()["clip"]
    report.check(f"{entry['id']}_published_ready", clip.get("mediaStatus") == "ready")
    return {"clip_id": clip["id"], "status": "published", "video_url": clip["videoURL"],
            "video_sha256": sha256(video.read_bytes()), "duration": duration}


def write_ledger(path, ledger):
    """Replace the ledger whole or not at all: a half-written one blocks every rerun."""
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w") as handle:
        json.dump(ledger, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def ingest(args):
    entries = load_manifest(args.manifest)
    gate = validate_manifest(entries, args.minimum)
    if gate["status"] != "passed" and not args.partial:
        # Nothing reaches the public feed from a manifest that fails review.
        print(json.dumps(gate, indent=2))
        print("The manifest gate failed and nothing was uploaded. Fix the problems above, "
              "or pass --partial to publish only the entries that are ready.", file=sys.stderr)
        return 1
    approved = [e for e in entries if (e.get("review") or {}).get("approved") is True and not entry_problems(e)]
    ledger_path = Path(args.ledger)
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    report = Report("catalog_ingest", args.api)
    report.data["manifest_gate"] = gate
    with httpx.Client(base_url=args.api, timeout=300, transport=PatientTransport(httpx.HTTPTransport())) as api, \
            httpx.Client(timeout=600, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as sources:
        auth = {"Authorization": f"Bearer {authenticate(api)}"}
        for entry in approved:
            if entry["id"] in ledger:
                continue
            with tempfile.TemporaryDirectory() as folder:
                try:
                    result = ingest_entry(api, auth, sources, entry, report, Path(folder))
                except Exception as error:  # noqa: BLE001 - one bad source must not stop the rest
                    report.check(f"{entry['id']}_ingested", False, error=f"{type(error).__name__}: {error}"[:300])
                    continue
            report.check(f"{entry['id']}_ingested", True, clip_id=result["clip_id"])
            ledger[entry["id"]] = {**result, "source": entry["source"], "attribution": attribution_line(entry["source"])}
            write_ledger(ledger_path, ledger)
    published = sum(1 for e in approved if e["id"] in ledger)
    report.check("catalog_meets_minimum", published >= args.minimum, published=published, minimum=args.minimum)
    report.data["attribution_records"] = {key: value["attribution"] for key, value in ledger.items()}
    return 0 if report.finish(args.report) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search")
    find.add_argument("source", choices=["nasa", "commons"])
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=10)
    check = sub.add_parser("validate")
    check.add_argument("--manifest", required=True)
    check.add_argument("--minimum", type=int, default=20)
    load = sub.add_parser("ingest")
    load.add_argument("--manifest", required=True)
    load.add_argument("--api", required=True)
    load.add_argument("--ledger", default="discover-catalog-ledger.json")
    load.add_argument("--minimum", type=int, default=20)
    load.add_argument("--report")
    load.add_argument("--partial", action="store_true",
                      help="publish the ready entries even when the manifest gate fails")
    args = parser.parse_args(argv)
    return {"search": search, "validate": validate, "ingest": ingest}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
