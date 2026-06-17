# Staging Validation — confirming real LLM output quality

The automated test suite (`tests/test_adaptive_tutor.py`) proves the adaptive
tutor is **wired correctly**, but it runs keyless: every LLM call deliberately
falls back to a deterministic template. That validates structure and graceful
degradation — it does **not** validate the quality of real model output.

This kit closes that gap. Run it where the API keys live.

## What it checks

| Feature | What "good" looks like |
|---|---|
| AI provider probe | a configured model returns `PONG` with `is_fallback=False` |
| Greeting | a warm, varied greeting (not "temporarily unable…") |
| Chat tutoring | for a **frustrated** learner: empathetic tone + a worked example before a question (the coaching directive working on real output) |
| Identity arc | deterministic — shown for sanity, not an LLM check |
| Group challenge | a real, on-topic collaborative problem; server reports `degraded=false` |
| Moderation summary | a real recap; `degraded=false` |

It classifies every AI response as **REAL** or **FALLBACK/DEGRADED** (matching
the resilience manager's fallback phrases / the server's `degraded` flag) and
prints the actual text so you can judge quality by hand. Exit code is `0` only
if every exercised AI path returned real model output.

## How to run

### Option A — on Railway (richest signal)

Run in the environment that already has `GEMINI_API_KEY` set. This boots the app
in-process, seeds a frustrated learner weak in quadratics, and shows the full
personalized output:

```bash
python scripts/staging_validation.py --in-process
```

(If running locally instead, export the key first:
`GEMINI_API_KEY=... python scripts/staging_validation.py --in-process`.)

### Option B — against the live deployment over HTTP

Validates the actual running Railway box from anywhere. Registers a throwaway
user and classifies each response. (Remote mode can't seed mastery/affect, so
personalization depth is limited — but REAL-vs-FALLBACK is still authoritative.)

```bash
python scripts/staging_validation.py --base-url https://<your-app>.up.railway.app
```

## Interpreting results

- **All REAL (exit 0):** the credential plumbing works end to end; judge the
  printed text for tone/accuracy.
- **Any FALLBACK/DEGRADED (exit 1):** the AI layer degraded. Check, in order:
  1. `GEMINI_API_KEY` (or `GOOGLE_API_KEY` / `OPENAI_API_KEY`) is set in the
     running process — the in-process probe prints which models are configured.
  2. The circuit breaker isn't open from earlier failures (it auto-resets after
     the cooldown, or restart the process / hit
     `POST /ai/admin/circuit-breaker/reset`).
  3. Redis is reachable if you expect cache hits (optional — absence only
     disables caching, it does not cause fallbacks).

## Notes

- The throwaway users this creates are harmless but do persist; clean them up if
  you run against a long-lived staging DB.
- This does not assert exact wording (model output varies). It is a
  human-in-the-loop quality gate, not a regression test.
