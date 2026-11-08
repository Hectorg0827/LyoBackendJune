# Staging-only FastKokoro ONNX teacher voice pilot

Date: 2026-11-07 (America/New_York)

## Why this exists

The original Railway CPU Kokoro-FastAPI image failed repeated redeploy
healthchecks despite eventually opening its server port. The previously
healthy deployment remained available to the classroom. For a reversible
comparison, `LyoTeacherOnnxPilot` was created as a **separate private staging
service**. It does not receive classroom requests.

## Isolated pilot configuration

- Railway project: `LyoOne-Journey-Staging`, environment: `staging`
- Service: `LyoTeacherOnnxPilot`
- Private URL: `http://lyoteacheronnxpilot.railway.internal:8880`
- Image: `msgflux/fastkokoro:cpu` (mutable tag; pin an immutable digest before
  a sustained rollout)
- Limits: 1 vCPU, 2 GB memory; execution provider: `CPUExecutionProvider`
- ONNX inter-/intra-op threads: `1` each
- Warmup enabled, sentence streaming strategy, `/health` readiness probe
- No public domain, paid voice provider, or production deployment

## Observed acceptance tests

Tests called the private endpoint from `LyoJourneyStagingBackend`'s staging
console. `curl` transfer start timings are *not* measurements of acoustic
playback in a browser.

| Request | Result | Start of response | Full transfer |
| --- | --- | ---: | ---: |
| English `af_heart`, WAV, short utterance | 200 | 1.72 s | 1.72 s |
| Spanish `ef_dora`, WAV, short utterance | 200 | 1.65 s | 1.65 s |
| English `af_heart`, MP3 streaming, speed 1.0 | 200 | 1.72 s | 1.72 s |
| Spanish `ef_dora`, MP3 streaming, explicit `lang=es-es` | 200 | 1.78 s | 3.61 s |
| LYO character `am_liam`, longer MP3 streaming | 200 | 1.66 s | 6.53 s |
| LYO's original 0.98 speed without adapter | **422** | — | — |

Initial service startup took about six seconds and passed Railway healthcheck.
The service held about 1.64 GB of RAM after warmup, leaving limited headroom
under the configured 2 GB cap. Concurrency/peak memory and listening quality
are **not yet accepted**.

## Opt-in backend adapter

The backend keeps `TTS_PROVIDER=kokoro` and chooses its HTTP request adapter
with the new `KOKORO_TTS_RUNTIME` variable:

- `fastapi` (default): existing Kokoro-FastAPI payload and cache keys.
- `fastkokoro`: sends `lang` based on the resolved voice locale, and clamps
  request speeds below 1.0 to 1.0 to avoid FastKokoro's HTTP 422. It also
  partitions the audio cache by runtime.

Test locally with:

```bash
.venv/bin/python -m pytest -q tests/tts/test_fastkokoro_compat.py tests/tts/test_service.py
```

## Next acceptance gates, in order

1. Pin the pilot image digest or reviewed release to make redeploys reproducible.
2. Verify all configured English cast voices and the Spanish teacher audio by
   listening to complete recordings; check pronunciation, pacing and silence.
3. Measure memory/CPU and first audio under 2-3 simultaneous classroom turns;
   resize the service before load if memory approaches its 2 GB limit.
4. Deploy the adapter to **staging backend only** while keeping its default
   runtime `fastapi`. Confirm old-path health and no changes to paid billing.
5. Change only staging backend `KOKORO_TTS_BASE_URL` to this private service
   and `KOKORO_TTS_RUNTIME=fastkokoro`. Perform a Web and Android classroom
   session including English and Spanish with latency and audio checks.
6. Restore the original URL and `fastapi` runtime immediately if speech
   regresses. No production promotion until an independently reviewed gate.

The pilot is a running Railway service and may incur normal compute charges.
Turn it off when the evaluation is complete; it is not a free idle artifact.
