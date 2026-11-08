"""Opt-in, no-paid-API voice QA for the private FastKokoro ONNX pilot.

Run this from a staging container with access to the private ONNX endpoint::

    python scripts/onnx_voice_quality_check.py \
        --base-url http://lyoteacheronnxpilot.railway.internal:8880

The five generated MP3s and JSON metadata report are written only to the
specified output directory. Passing metadata checks is *not* a substitute
for listening to every sample and checking pronunciation and natural pacing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


# Deliberately short but representative, including two distinct English
# characters and Spanish-specific punctuation/diacritics.
VOICE_SAMPLES = (
    {
        "id": "en_welcome",
        "locale": "en-US",
        "lang": "en-us",
        "voice": "af_heart",
        "input": "Welcome back! Are you ready to learn something wonderful today?",
        "listen_for": "Warm opening, question intonation, natural pause after 'back'.",
    },
    {
        "id": "en_fractions",
        "locale": "en-US",
        "lang": "en-us",
        "voice": "af_heart",
        "input": "Let's compare one third and one fourth. Which fraction is larger?",
        "listen_for": "Clear 'one third'/'one fourth', pause at period, rising question.",
    },
    {
        "id": "en_lyo_character",
        "locale": "en-US",
        "lang": "en-us",
        "voice": "am_liam",
        "input": "Hmm, I think I know! Negative two is less than zero, right?",
        "listen_for": "A distinct male Lyo voice, 'negative two', curious intonation.",
    },
    {
        "id": "es_welcome",
        "locale": "es-US",
        "lang": "es-es",
        "voice": "ef_dora",
        "input": "¡Hola, clase! ¿Están listos para descubrir algo maravilloso hoy?",
        "listen_for": "Natural Spanish accents, exclamation/question contours, no English sounds.",
    },
    {
        "id": "es_fractions",
        "locale": "es-US",
        "lang": "es-es",
        "voice": "ef_dora",
        "input": "Un tercio es mayor que un cuarto. ¿Cuánto es tres coma cinco menos dos?",
        "listen_for": "Correct 'tercio', 'cuarto', 'tres coma cinco', smooth sentence break.",
    },
)


def _probe(path: Path) -> dict:
    """Probe actual MP3 duration/codec when ffprobe is installed."""
    if not shutil.which("ffprobe"):
        return {"probe_available": False}
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,bit_rate:stream=codec_name,sample_rate,channels",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        return {"probe_available": True, "probe_error": result.stderr.strip()[:200]}
    parsed = json.loads(result.stdout)
    audio = next((s for s in parsed.get("streams", []) if s.get("codec_name") == "mp3"), {})
    fmt = parsed.get("format", {})
    return {
        "probe_available": True,
        "duration_s": round(float(fmt.get("duration", 0)), 2),
        "codec": audio.get("codec_name"),
        "sample_rate_hz": int(audio.get("sample_rate", 0)),
        "channels": audio.get("channels"),
        "bit_rate": int(fmt.get("bit_rate", 0)),
    }


def check_sample(base_url: str, case: dict, out_dir: Path, timeout: int) -> dict:
    payload = {
        "model": "kokoro", "input": case["input"], "voice": case["voice"],
        "lang": case["lang"], "response_format": "mp3", "speed": 1.0,
        "stream": True,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/audio/speech",
        json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    start = time.perf_counter()
    out_file = out_dir / f"{case['id']}.mp3"
    result = {key: case[key] for key in ("id", "locale", "lang", "voice", "input", "listen_for")}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["http_status"] = response.status
            result["content_type"] = response.headers.get("Content-Type", "")
            with out_file.open("wb") as target:
                first = response.read(8192)
                result["first_audio_s"] = round(time.perf_counter() - start, 2)
                target.write(first)
                while chunk := response.read(8192):
                    target.write(chunk)
            result["transfer_s"] = round(time.perf_counter() - start, 2)
        raw = out_file.read_bytes()
        result["bytes"] = len(raw)
        result["sha256"] = hashlib.sha256(raw).hexdigest()
        result.update(_probe(out_file))
        result["metadata_pass"] = (
            result["http_status"] == 200
            and result["content_type"].startswith("audio/mpeg")
            and len(raw) > 1000
            and (raw.startswith(b"ID3") or (raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0))
            and not result.get("probe_error")
            and (not result.get("probe_available") or 0.5 < result.get("duration_s", 0) < 45)
        )
    except (OSError, urllib.error.HTTPError) as exc:
        result["metadata_pass"] = False
        result["error"] = str(exc)[:200]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Private staging FastKokoro origin")
    parser.add_argument("--output-dir", default="/tmp/lyo-onnx-voice-qa")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = [check_sample(args.base_url, case, out_dir, args.timeout) for case in VOICE_SAMPLES]
    (out_dir / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for item in results:
        print(f"VOICE_QA {item['id']}: {'PASS' if item['metadata_pass'] else 'FAIL'} "
              f"first={item.get('first_audio_s')}s total={item.get('transfer_s')}s "
              f"bytes={item.get('bytes')} duration={item.get('duration_s')}")
    print("Audio and metadata:", out_dir)
    print("IMPORTANT: Subjective listening/pronunciation gate remains PENDING.")
    return 0 if all(item["metadata_pass"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
