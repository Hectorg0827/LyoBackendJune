# LYO Classroom — Google Chirp 3 HD staging pilot

This is an opt-in, staging-only voice latency comparison. Do **not** switch
production, SecretaryAI, the separate VoiceLab or any shared production key.

## Preconditions before enabling

1. Confirm the earlier temporary CPU experiment's actual Railway usage against
   the user's **$25 total cap**. This pilot permits no more than **$15** of
   additional estimated Google Chirp API requests; reduce it if less remains.
2. In **Default Gemini Project (`gen-lang-client-0277145511`)**, which has
   active billing, enable Text-to-Speech API, apply a Google-side budget alert
   and low API quota. Google budget alerts are not hard spending stops, and
   project-level Gemini usage is separate from this trial. Never reuse the
   Gemini API key.
3. Use a dedicated, least-privileged **service account** with OAuth/ADC for
   the documented REST `POST /v1/text:synthesize`; the Gemini API key is not
   suitable authentication for this endpoint. Prefer short-lived workload
   identity federation where Railway identity support permits it. A manually
   created service-account key is a fallback only with explicit approval and
   secret storage. Do not create a key or start billable calls by default.
4. Verify staging Redis is connected, persists the trial ledger, and uses an
   appropriate non-evicting policy. If Redis fails, requests fail closed.
5. In **LyoJourneyStagingBackend** only, store the dedicated service-account
   JSON in sealed `GOOGLE_TTS_SERVICE_ACCOUNT_JSON` or configure
   `GOOGLE_APPLICATION_CREDENTIALS` to point to a credentials file provided
   securely by the deployment system. Never place any credential in GitHub,
   chat messages, logs or a URL. No ambient Gemini key fallback is permitted.

## Controlled activation (only after preconditions pass)

Set only in the staging environment:

```
ENVIRONMENT=staging
TTS_CHIRP_TRIAL_ENABLED=true
TTS_CHIRP_TRIAL_LIMIT_USD=15.00
TTS_PROVIDER=google
```

The pilot code charges a separate, no-TTL Redis ledger before *each* uncached
request, reserving **$40 per million UTF-8 bytes**, above the currently
published Chirp 3 HD **$30 per million characters**. Timeouts are never
refunded. It refuses to run outside staging, with a missing/oversized limit,
or without Redis. Cache hits do not incur another provider request.

The Redis reservation bounds *this service's estimated voice request usage*,
not the external Google Cloud invoice, taxes, billing delays, or other project
usage. A strict global financial cap cannot be guaranteed solely by code or
ordinary Google budget alerts.

## Acceptance comparison

- Use identical 25-, 75- and 150-character utterances for Kokoro and Chirp.
- Measure p50/p95 first-audio time, total completion, errors/timeouts,
  and cost-reserved per utterance across at least 10 runs each.
- Listen to teacher pacing, Spanish pronunciation and voice consistency.
- Verify the browser never silently switches the teacher's voice mid-lesson.
- Confirm learner progression and interactions remain usable if TTS fails.
- Google REST currently returns full base64 audio before forwarding: a fast
  result is possible, but this integration is **not true audio streaming**.
  If results are good but first audio is still slow, evaluate Chirp's
  streaming-synthesis API separately (requires ADC/service-account auth).

## Immediate rollback

Set `TTS_PROVIDER=kokoro` and `TTS_CHIRP_TRIAL_ENABLED=false` on **staging only**.
Retain the Redis ledger for audit; never erase it to reset the trial.
