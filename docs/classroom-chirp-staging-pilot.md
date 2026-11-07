# LYO Classroom — Google Chirp 3 HD staging pilot

This is an opt-in, staging-only voice latency comparison. Do **not** switch
production, SecretaryAI, the separate VoiceLab or any shared production key.

## Preconditions before enabling

1. Confirm the earlier temporary CPU experiment's actual Railway usage against
   the user's **$25 total cap**. This pilot permits no more than **$15** of
   additional estimated Google Chirp API requests; reduce it if less remains.
2. Create a billing-enabled Google Cloud project restricted to this experiment,
   enable Text-to-Speech API, and apply a Google-side budget alert, API quota,
   and API-specific credential restriction. Alerts are not hard spending stops.
   Do not reuse `GEMINI_API_KEY`, which serves another function.
3. Confirm the selected Google Cloud credential supports REST
   `POST /v1/text:synthesize`. Google's TTS documentation primarily describes
   ADC/OAuth; an API key must be verified before enabling the classroom switch.
4. Verify staging Redis is connected, persists the trial ledger, and uses an
   appropriate non-evicting policy. If Redis fails, requests fail closed.
5. In **LyoJourneyStagingBackend** only, store a dedicated credential as a
   sealed `GOOGLE_TTS_API_KEY` environment variable. Never place it in GitHub,
   chat messages, logs or a URL.

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
