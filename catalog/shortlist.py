"""Turn raw search drafts into a review list a person can work through.

Reads the drafts `discover_catalog.py search` printed (one JSON object per
line, each tagged with the area and query that found it), drops repeats,
probes every video at its source with ffprobe, and writes:

  catalog/drafts.jsonl    one unapproved draft per line, subject set to the
                          area that found it, plus a "probe" record
  catalog/CANDIDATES.md   the same list as a table to review: watch link,
                          length, size, licence, credit, and why a video
                          cannot be used when it cannot

Nothing here approves anything. A person still watches each video and sets
review.approved, factChecked, ageAppropriate, rightsCleared and reviewer.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "scripts"))
from discover_catalog import MIN_SECONDS, licence_family  # noqa: E402


def probe_remote(url):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-user_agent", "LyoDiscoverCatalog/1.0 (https://lyoai.app; library ingestion)",
             "-print_format", "json", "-show_streams", "-show_format", url],
            check=True, capture_output=True, text=True, timeout=90).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}
    info = json.loads(out)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    return {"duration": round(duration, 1), "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0), "audio": audio}


def blockers(entry):
    probe, source = entry["probe"], entry["source"]
    found = []
    if not licence_family(source.get("license")):
        found.append(f"licence {source.get('license')!r} not allowed")
    if not (source.get("credit") or "").strip():
        found.append("no credit")
    if "error" in probe:
        found.append("video could not be read")
    else:
        if probe["duration"] < MIN_SECONDS:
            found.append(f"only {probe['duration']}s long")
        if min(probe["width"], probe["height"]) < 360:
            found.append(f"{probe['width']}x{probe['height']} is below 360p")
    if not entry["review"]["rightsCleared"]:
        found.append("mentions another rights holder: check before use")
    return found


def main(raw_path, out_dir):
    seen, entries = set(), []
    for line in Path(raw_path).read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        key = entry["source"]["mediaUrl"]
        if entry["id"] in seen or key in seen:
            continue
        seen.update({entry["id"], key})
        entries.append(entry)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for entry, probe in zip(entries, pool.map(probe_remote, [e["source"]["mediaUrl"] for e in entries])):
            entry["probe"] = probe
    for entry in entries:
        entry["subject"] = entry.pop("area")
        entry["blockers"] = blockers(entry)

    out = Path(out_dir)
    (out / "drafts.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))
    usable = [e for e in entries if not e["blockers"]]
    lines = [
        "# Discover library candidates",
        "",
        f"{len(entries)} videos found, {len(usable)} usable as they stand. Nothing here is approved.",
        "Watch each one from its link before choosing it.",
        "",
        "| # | Subject | Title | Length | Size | Licence | Credit | Can it be used? |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for number, entry in enumerate(entries, 1):
        probe, source = entry["probe"], entry["source"]
        length = f"{probe['duration']:.0f}s" if "duration" in probe else "?"
        size = f"{probe['width']}x{probe['height']}" if "width" in probe else "?"
        title = entry["title"].replace("|", "/")[:90]
        verdict = "yes" if not entry["blockers"] else "no: " + "; ".join(entry["blockers"])
        lines.append(f"| {number} | {entry['subject']} | [{title}]({source['pageUrl']}) | {length} | {size} "
                     f"| {source.get('license') or '?'} | {(source.get('credit') or '?').replace('|', '/')[:60]} "
                     f"| {verdict} |")
    (out / "CANDIDATES.md").write_text("\n".join(lines) + "\n")
    print(f"{len(entries)} candidates, {len(usable)} usable")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
