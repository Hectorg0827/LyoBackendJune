"""The STEM library tool: licences, source parsing, review gate and encoding.

The source payloads below are trimmed to the fields the tool reads from the
NASA Image and Video Library and Wikimedia Commons APIs. They exercise the
parsing; they are not library entries.
"""
import json
import shutil
from fractions import Fraction
import subprocess

import pytest

from scripts import discover_catalog as catalog

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


@pytest.mark.parametrize("name,family", [
    ("Public domain", "public-domain"),
    ("PD-USGov-NASA", "public-domain"),
    ("CC0", "cc0"),
    ("CC BY 4.0", "cc-by"),
    ("CC-BY-3.0", "cc-by"),
    ("CC BY-SA 4.0", "cc-by-sa"),
    ("CC BY-NC 4.0", None),
    ("CC BY-NC-SA 3.0", None),
    ("CC BY-ND 4.0", None),
    ("GFDL", None),
    ("All rights reserved", None),
    ("", None),
    (None, None),
])
def test_only_commercially_reusable_adaptable_licences_are_allowed(name, family):
    assert catalog.licence_family(name) == family


def test_nasa_search_results_become_unapproved_drafts_with_their_credit():
    href = "https://images-assets.nasa.gov/video/X1/collection.json"
    body = {"collection": {"items": [
        {"href": href, "data": [{"nasa_id": "X1", "media_type": "video", "title": "Rover landing",
                                 "center": "JPL", "description": "<p>Entry, descent &amp; landing.</p>",
                                 "keywords": ["Mars", "rover"]}]},
        {"href": "https://images-assets.nasa.gov/image/Y/collection.json",
         "data": [{"nasa_id": "Y", "media_type": "image", "title": "A photo"}]},
    ]}}
    collections = {href: ["http://images-assets.nasa.gov/video/X1/X1~orig.mp4",
                          "http://images-assets.nasa.gov/video/X1/X1~medium.mp4",
                          "http://images-assets.nasa.gov/video/X1/X1~thumb.jpg"]}
    [entry] = catalog.nasa_entries(body, collections)
    assert entry["id"] == "nasa-X1"
    assert entry["description"] == "Entry, descent & landing."
    assert entry["source"]["mediaUrl"] == "https://images-assets.nasa.gov/video/X1/X1~medium.mp4"
    assert entry["source"]["credit"] == "NASA/JPL"
    assert entry["source"]["license"] == "Public domain"
    assert entry["review"]["approved"] is False
    assert entry["review"]["rightsCleared"] is True


def test_nasa_material_that_mentions_another_owner_needs_rights_clearance():
    href = "https://images-assets.nasa.gov/video/Z/collection.json"
    body = {"collection": {"items": [{"href": href, "data": [{
        "nasa_id": "Z", "media_type": "video", "title": "Concert", "description": "Footage courtesy of a TV network."}]}]}}
    [entry] = catalog.nasa_entries(body, {href: ["https://images-assets.nasa.gov/video/Z/Z~small.mp4"]})
    assert entry["review"]["rightsCleared"] is False


def test_commons_results_keep_the_licence_the_file_page_reports():
    body = {"query": {"pages": [
        {"pageid": 7, "title": "File:Mitosis_in_onion_cells.webm", "imageinfo": [{
            "url": "https://upload.wikimedia.org/a/b/Mitosis.webm", "mime": "video/webm",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Mitosis_in_onion_cells.webm",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                            "Artist": {"value": "<a href='/wiki/User:X'>Jane Doe</a>"},
                            "ImageDescription": {"value": "Time-lapse of <b>mitosis</b>."}}}]},
        {"pageid": 8, "title": "File:Diagram.png", "imageinfo": [{"url": "https://upload.wikimedia.org/x.png",
                                                                   "mime": "image/png"}]},
        {"pageid": 9, "title": "File:Lecture.webm", "imageinfo": [{
            "url": "https://upload.wikimedia.org/c/d/Lecture.webm", "mime": "video/webm",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Lecture.webm",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 2.0"}}}]},
    ]}}
    mitosis, lecture = catalog.commons_entries(body)
    assert mitosis["title"] == "Mitosis in onion cells"
    assert mitosis["source"]["credit"] == "Jane Doe"
    assert mitosis["source"]["license"] == "CC BY-SA 4.0"
    assert mitosis["description"] == "Time-lapse of mitosis."
    assert lecture["review"]["rightsCleared"] is False


def approved(entry_id, subject="Biology", **changes):
    entry = {
        "id": entry_id, "title": f"Clip {entry_id}", "subject": subject, "level": "beginner", "tags": [],
        "source": {"name": "Wikimedia Commons", "pageUrl": f"https://commons.wikimedia.org/wiki/File:{entry_id}.webm",
                   "mediaUrl": f"https://upload.wikimedia.org/{entry_id}.webm", "license": "CC BY 4.0",
                   "credit": "Jane Doe"},
        "review": {"approved": True, "reviewer": "Hector", "factChecked": True, "ageAppropriate": True,
                   "rightsCleared": True},
    }
    for key, value in changes.items():
        if key in ("source", "review"):
            entry[key] = {**entry[key], **value}
        else:
            entry[key] = value
    return entry


def test_the_gate_needs_twenty_cleared_reviewed_entries():
    subjects = ["Astronomy", "Biology", "Chemistry", "Physics", "Math"]
    entries = [approved(f"e{i}", subjects[i % 5]) for i in range(20)]
    result = catalog.validate_manifest(entries, 20)
    assert result["status"] == "passed"
    assert {"astronomy", "biology", "chemistry", "physics", "math"} <= set(result["areas_covered"])
    assert "robotics" in result["areas_missing"]

    entries[0] = approved("e0", source={"license": "CC BY-NC 4.0"})
    entries[1] = approved("e1", review={"factChecked": False})
    entries[2] = approved("e2", source={"mediaUrl": "https://www.youtube.com/watch?v=x"})
    blocked = catalog.validate_manifest(entries, 20)
    assert blocked["status"] == "failed"
    assert set(blocked["problems"]) == {"e0", "e1", "e2"}
    assert blocked["ready"] == 17


def test_drafts_do_not_count_toward_the_library():
    draft = approved("d1", review={"approved": False})
    assert catalog.validate_manifest([draft], 1)["ready"] == 0


def test_attribution_line_names_creator_and_licence():
    assert catalog.attribution_line({"credit": "NASA/JPL", "license": "Public domain"}) == "NASA/JPL · Public domain"


def test_downloads_are_limited_to_source_hosts():
    with pytest.raises(ValueError):
        catalog.download(None, "https://example.com/video.mp4", "/tmp/never-written")


def make_source(path, seconds=8, size="1920x1080", audio=True):
    command = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=60:duration={seconds}"]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=500:duration={seconds}"]
    # A WebM like most Commons uploads: VP9 video, Opus audio, index at the end.
    command += ["-c:v", "libvpx-vp9", "-b:v", "1M", "-deadline", "realtime"]
    command += ["-c:a", "libopus"] if audio else []
    subprocess.run(command + [str(path)], check=True)


@needs_ffmpeg
@pytest.mark.parametrize("audio", [True, False])
def test_encoding_produces_a_phone_friendly_mp4_and_poster(tmp_path, audio):
    source = tmp_path / "source.webm"
    make_source(source, audio=audio)
    out, poster = tmp_path / "clip.mp4", tmp_path / "poster.jpg"
    duration = catalog.encode(source, out, poster, start=1, duration=5)
    assert 4.5 <= duration <= 5.5
    info = catalog.probe(out)
    assert info["video"]["codec_name"] == "h264" and info["audio"]["codec_name"] == "aac"
    assert max(int(info["video"]["width"]), int(info["video"]["height"])) <= 1280
    assert info["video"]["pix_fmt"] == "yuv420p"
    assert float(Fraction(info["video"]["avg_frame_rate"])) <= 30.01
    assert catalog.index_at_front(out)
    assert poster.stat().st_size > 0


@needs_ffmpeg
def test_too_short_or_too_small_sources_are_refused(tmp_path):
    short, small = tmp_path / "short.webm", tmp_path / "small.webm"
    make_source(short, seconds=3)
    make_source(small, size="320x240")
    with pytest.raises(ValueError, match="at least"):
        catalog.encode(short, tmp_path / "a.mp4", tmp_path / "a.jpg", 0, None)
    with pytest.raises(ValueError, match="360p"):
        catalog.encode(small, tmp_path / "b.mp4", tmp_path / "b.jpg", 0, None)


@needs_ffmpeg
def test_an_index_at_the_end_is_detected(tmp_path):
    late = tmp_path / "late.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:duration=2",
                    "-c:v", "libx264", str(late)], check=True)
    assert catalog.index_at_front(late) is False


def test_validate_command_reports_and_exits_nonzero_below_minimum(tmp_path, capsys):
    manifest = tmp_path / "catalog.json"
    manifest.write_text(json.dumps({"entries": [approved("only")]}))
    assert catalog.main(["validate", "--manifest", str(manifest)]) == 1
    assert json.loads(capsys.readouterr().out)["ready"] == 1


def test_a_failed_gate_uploads_nothing(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "catalog.json"
    manifest.write_text(json.dumps({"entries": [approved("only")]}))

    def no_network(*_args, **_kwargs):
        raise AssertionError("ingest must stop before signing in or uploading")

    monkeypatch.setattr(catalog, "authenticate", no_network)
    monkeypatch.setattr(catalog, "ingest_entry", no_network)
    code = catalog.main(["ingest", "--manifest", str(manifest), "--api", "http://127.0.0.1:9",
                         "--ledger", str(tmp_path / "ledger.json")])
    assert code == 1
    assert "nothing was uploaded" in capsys.readouterr().err
    assert not (tmp_path / "ledger.json").exists()


def test_the_ledger_is_replaced_whole(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text('{"old": {}}')
    catalog.write_ledger(ledger, {"nasa-X1": {"clip_id": "7"}})
    assert json.loads(ledger.read_text()) == {"nasa-X1": {"clip_id": "7"}}
    assert [p.name for p in tmp_path.iterdir()] == ["ledger.json"]
