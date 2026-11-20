# LYO GPT-Live voice-quality trial — STAGING ONLY

**Not a production release. Do not merge/deploy this draft PR to production.**
This experiment compares LYO's current tap-based Android recognizer/TTS path
with continuously streamed GPT-Live audio (natural interruptions; no beeps).

## Trial economics and hard-stop rules

- Exact cumulative app cap: **$10.00 USD**. This fixed value cannot be raised by environment variables.
- Official current GPT-Live rate: **$0.05/minute**, per second. Recheck before enabling.
- Each ticket **permanently reserves $0.15** regardless of completion or error.
  This is 3x the expected cost of a 60-second trial session.
- At most **66** sessions can be authorized ($9.90 reserved). A 67th
  fails closed even with multiple servers and concurrent requests.
- Each provider WebSocket is **owned by the backend**, with a **60-second
  server-side wall-clock timeout** covering connection, speech and shutdown.
  The phone cannot lengthen this timeout or talk directly to OpenAI.
- PostgreSQL/SQLite single-row atomic conditional update in
  `lyo_gpt_live_trial_budget` enforces the shared cap. A separate table holds
  SHA-256 hashes of **single-use, 45-second tickets**. The raw ticket is
  never stored. Stale/missing DB -> deny provider access, never refund.
- Client delegation is **local deterministic sample curriculum**, no Responses,
  web search or extra paid model/tool invocations. No external learner memory,
  grades, or course state is accessed.
- `store: false` for the voice session. Audio/transcripts are relayed, not
  written to application logs or persisted. Only session duration is audited.
- Multiple layers prevent use: staging environment, exact staging host,
  dedicated **staging-only** OpenAI key, feature switch, authenticated
  user allowlist, DB cap, single-use ticket, and WebSocket cutoff.
- A dedicated OpenAI *staging project* and secondary platform budget alert/
  spend limit are strongly recommended before real spend. Other activity on
  a shared OpenAI account is **not** included in this application cap.

## Required staging configuration

Leave **`LYO_GPT_LIVE_TRIAL_ENABLED=false`** until CI, offline
safety tests, manual review and a separate staging backend are verified.

After all checks and an explicit paid activation checkpoint:

```text
ENVIRONMENT=staging
RAILWAY_ENVIRONMENT_NAME=staging  # if deployed on Railway
LYO_GPT_LIVE_STAGING_HOST=<exact-hostname-of-dedicated-staging-backend>
LYO_GPT_LIVE_TRIAL_ALLOWED_USER_IDS=<comma-separated-internal-user-ids>
LYO_GPT_LIVE_STAGING_OPENAI_API_KEY=<dedicated-project-key>
LYO_GPT_LIVE_TRIAL_ENABLED=true
```

Do **not** set any of these in the production Railway service or use the
production OpenAI key. Staging needs separate DB, key and backend URL.
Never put the OpenAI key in an Android APK, web bundle or Git repository.

Native Android trial UI also requires a **debug/staging** build with
`LYO_STAGING_API_BASE_URL` pointing to that dedicated staging service
and `LYO_GPT_LIVE_TRIAL_UI=true`. A release APK always compiles it off.

## HTTP / WebSocket protocol

1. Signed-in Android client requests `POST /api/v1/gpt-live-trial/ticket`
   over HTTPS with its existing bearer token.
2. Backend authenticates the user, checks all gates and atomically reserves
   $0.15. If it fails or the remaining cap cannot cover a full reservation,
   no ticket is issued.
3. Phone connects to `wss://<staging-host>/api/v1/gpt-live-trial/stream`,
   sending the one-use ticket in the `X-Lyo-Live-Ticket` header.
4. After `{"type":"ready"}`, phone sends 24 kHz mono signed PCM16
   chunks as base64 JSON `{"type":"audio","audio":"..."}`. Server returns
   `{"type":"audio","audio":"..."}`, and streamed `transcript` captions.
   A natural speech interruption needs no control message.
5. Phone can send `{"type":"end"}`; otherwise server closes at the hard
   60-second deadline. Server maintains the spend reservation on any error.
6. Original TextToSpeech/SpeechRecognizer remains the legacy fallback; the
   premium UI and current working APK are unchanged.

## Verification gates (before enabling the paid flag)

- [ ] Backend CI and offline budget tests pass, including concurrent issuance,
  expiry, replay, 67th session denial, and all staging/production gates.
- [ ] Android compile/tests pass with trial feature compiled **off** by default.
- [ ] Review code for logging, backend passthrough, key exposure and bypasses.
- [ ] Configure separate staging backend, database, dedicated OpenAI project/key.
- [ ] In a deliberately disabled staging test, verify endpoints cannot open
  a paid connection, including production host/production environment.
- [ ] Enable the flag **only after** the above safeguards have been verified and
  an explicit paid-usage checkpoint is approved.
- [ ] Test first short real session in headphones, then phone speaker and
  Bluetooth; verify echo suppression, duplex interruptions and sample captions.
- [ ] Cross-check actual provider usage against the trial ledger and project bill.
- [ ] Stop if pricing, key scope, listener behavior, timeout or usage diverges.

**STOP checkpoint:** This code is a draft only. No production deployment,
no activation flag, no OpenAI API call and no paid usage in this phase.

OpenAI docs:
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/voice-websockets
- https://developers.openai.com/api/docs/pricing
