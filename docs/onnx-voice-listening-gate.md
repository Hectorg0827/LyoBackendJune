# LYO ONNX pilot — English/Spanish listening acceptance

**Scope:** Railway staging `LyoTeacherOnnxPilot`, isolated from classroom traffic.
No paid TTS. No changes to the default classroom runtime until the gate passes.

## Reproducible samples

Run `scripts/onnx_voice_quality_check.py` with the private staging base URL.
It creates five MP3s and `report.json` in `/tmp/lyo-onnx-voice-qa` by default.
It verifies transport, MP3 signature, size, and codec/duration when `ffprobe`
is available. These mechanical checks **cannot** evaluate spoken quality.

| File | Speaker | Listening focus |
| --- | --- | --- |
| `en_welcome.mp3` | English teacher `af_heart` | Welcoming warmth, first pause, natural question intonation |
| `en_fractions.mp3` | English teacher `af_heart` | Unambiguous “one third”, “one fourth”, sentence break |
| `en_lyo_character.mp3` | Lyo `am_liam` | Distinct identity from teacher, “negative two”, curiosity |
| `es_welcome.mp3` | Spanish teacher `ef_dora` | Spanish phonemes, accents, `¡!` and `¿?` intonation |
| `es_fractions.mp3` | Spanish teacher `ef_dora` | “tercio”, “cuarto”, “tres coma cinco”, natural pauses |

## Human listening scorecard

Have a bilingual Spanish/English reviewer listen **at normal speed**, with
headphones and a phone speaker. Score each applicable area 1–5:

- Accurate words and numbers (especially fractions and decimals).
- Natural sentence and question intonation; pauses at logical boundaries.
- Clear, pleasant timbre without clicks, truncation, missing syllables or glitches.
- Consistent speaker identity; Lyo's voice sounds distinct from the teacher.
- Spanish accent fits the intended learner audience; flag any unintended
  European-versus-Latin-American pronunciation mismatch for product review.

**Acceptance:** All five sample recordings pass automated integrity checks,
each applicable listening score is at least 4/5, and there are zero critical
pronunciation errors, cut-off phrases, or unintelligible segments. Record
reviewer, date, scores, and exact MP3 hashes from the generated JSON. A
sample with failed playback, bad fractions, or a mispronounced mathematical
term is a blocker regardless of aggregate score.

## Live five-sample pilot run — November 8, 2026

All five private Railway ONNX requests returned **HTTP 200**, `audio/mpeg`,
and valid MP3 headers. Times below measure from request start to the first
actual received audio chunk, then to completion of the full transfer.

| Sample | First audio | Transfer | Bytes | Transport/format |
| --- | ---: | ---: | ---: | --- |
| `en_welcome` | 1.64 s | 3.28 s | 30,456 | PASS |
| `en_fractions` | 1.78 s | 3.45 s | 34,080 | PASS |
| `en_lyo_character` | 1.57 s | 6.35 s | 40,488 | PASS |
| `es_welcome` | 1.65 s | 5.01 s | 34,008 | PASS |
| `es_fractions` | 1.70 s | 3.30 s | 34,896 | PASS |

Five of five **transport and format** checks passed. Audio codec, duration,
clipping, and silence analysis via `ffprobe`/`ffmpeg` were **not performed** on
these particular responses; their audio files were not retained by the inline
console diagnostic. Repeat with `scripts/onnx_voice_quality_check.py` to save
the named MP3s and metadata when an accessible review location is arranged.

**Bilingual human listening gate: PENDING.** Do not mark pronunciation,
voice consistency, or natural pauses PASS using HTTP 200, file size, or latency.

### Reviewer record (complete before runtime promotion)

| Sample | Words/numbers 1–5 | Pacing 1–5 | Audio clarity 1–5 | Accent/voice 1–5 | Reviewer notes |
| --- | --- | --- | --- | --- | --- |
| `en_welcome` | — | — | — | — | — |
| `en_fractions` | — | — | — | — | — |
| `en_lyo_character` | — | — | — | — | — |
| `es_welcome` | — | — | — | — | — |
| `es_fractions` | — | — | — | — | — |

Reviewer name/date and MP3 SHA-256 values: **not yet recorded**.
