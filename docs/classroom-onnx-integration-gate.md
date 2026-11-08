# Classroom ONNX integration gate (staging only)

Last reviewed: 2026-11-08. This is a validation runbook, not approval to
change the active classroom voice runtime.

## Current routing and isolation

- Web and Android classroom clients can use the authenticated backend routes
  `POST /api/v1/tts/synthesize/stream` (MP3 bytes) and
  `POST /api/v1/tts/synthesize` (legacy base64 JSON).
- Both routes call the shared `TTSService`; the effective Kokoro runtime is
  selected **server-side** through `KOKORO_TTS_RUNTIME`.
- `fastapi` is the default runtime. `fastkokoro` is opt-in and requires the
  private pilot URL as `KOKORO_TTS_BASE_URL`.
- On 2026-11-08 the staging backend was live with a SUCCESS deployment, and
  the Railway service's variable-name inventory did **not** include
  `KOKORO_TTS_RUNTIME`; it therefore uses the backward-compatible default.
- `ALLOW_OPENAI_TTS=false` must remain in force. No paid provider is needed for
  this integration.

## Verified locally

`tests/tts/test_classroom_onnx_route_integration.py` exercises both HTTP routes
with a local mock of FastKokoro's OpenAI-compatible speech endpoint:

- English streaming Lyo uses cast voice `am_liam`, `lang=en-us`.
- Spanish streaming teacher uses `ef_dora`, `lang=es-es`.
- Both stream routes return audio/mpeg and no-store/no-buffer headers.
- Legacy base64 English teacher_3 uses `af_sky` and Spanish teacher_3 uses
  `ef_dora`; the public locale is preserved in the JSON response.
- The current classroom 0.98 speed is normalized to the pilot's accepted 1.0
  floor. Both routes keep `TTS_PROVIDER=kokoro` and never call a paid API.

Run from the backend checkout:

```bash
python -m pytest -q tests/tts/test_classroom_onnx_route_integration.py \
  tests/tts/test_fastkokoro_compat.py tests/tts/test_stream_route.py
```

These tests use mocked audio payloads. They prove HTTP and configuration
compatibility, **not acoustic quality, real browser playback, or the latency of
the deployed Railway pilot**.

## Safe live acceptance sequence

1. Pin the private ONNX image to an immutable release/digest and confirm
   available memory under classroom concurrency.
2. Listen to full audio samples in English and Spanish and verify all intended
   character voices, pauses, numbers, and fractions.
3. Confirm an explicit go/no-go for a temporary **staging-only** switch.
   Record the exact existing staging `KOKORO_TTS_BASE_URL` value privately as
   the rollback target; never copy credentials into reports.
4. Set only staging backend `KOKORO_TTS_BASE_URL` to the internal ONNX pilot
   and `KOKORO_TTS_RUNTIME=fastkokoro`; leave provider, paid-fallback settings,
   and production untouched. Wait for a terminal SUCCESS deployment.
5. Re-run English and Spanish Web/Android classroom sessions, user-visible
   audio playback, speech-to-text alignment, navigation/progression, and the
   30-minute live acceptance. Watch first-byte/first-play latency, 502s,
   interruptions, CPU/memory, and fallback behavior.
6. On speech regression or unacceptable latency, immediately restore the
   recorded previous staging URL and `KOKORO_TTS_RUNTIME=fastapi`, wait for
   SUCCESS, and verify the old route is healthy. Do not promote to production.

## Remaining integration blockers

- Classroom traffic has **not** been directed to the private ONNX pilot.
- Real browser playback and the 30-minute session are separate live gates.
- Three overlapping private-pilot calls previously required up to 8.51 s for
  first audio: this performance needs improvement before normal classroom use.
