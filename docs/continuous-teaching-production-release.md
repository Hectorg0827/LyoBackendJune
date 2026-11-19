# LYO Continuous Teaching — guarded production release

## Scope and source of truth

This release adds the ungraded AI-powered lesson kickoff and transition bridge to
Web and Android. The authoritative Classroom scene/grade engine is unchanged.

- Backend code: `Hectorg0827/LyoBackendJune`, release branch `release/lyo-continuous-teaching-gated-20261118`
- Web/Android code: `Hectorg0827/Lyo_Da_One`, same release branch
- Staging feature dependencies: backend draft PR #183 and Web/Android draft PR #240
- Baseline preview: separately deployed backend `fc046187`, Web `2ca0a7f8`
- Do not touch PR #210 or iOS as part of this release.

**All controls default OFF.** Shipping code does not authorize or turn on
production for any learner.

## Explicit feature gates (server is authoritative)

| Variable | Scope | Required before canary |
| --- | --- | --- |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED` | Backend production | `1` only after deployment, auth review and sign-off; `0` is the kill switch |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_USER_IDS` | Backend production | Nonempty comma-separated **server-authenticated JWT user IDs** for approved synthetic/canary test identities; wildcard `*` is never accepted |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_AI_ENABLED` | Backend production | `1` only after spend/price checks; `0` keeps local ungraded fallback |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_RATES_APPROVED` | Backend production | `1` only after independent price/model review; default `0` |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_TOTAL_BUDGET_USD` | Backend production | Explicit positive decimal, **maximum $50 total**; missing/invalid budget denies AI requests |
| `NEXT_PUBLIC_LYO_CONTINUOUS_TEACHING_PRODUCTION` | Web production build | `1` only for the canonical `api.lyoai.app` WebSocket, otherwise `0` |
| `LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED` | Android release build Gradle property | `1` enables app opt-in to canonical production API; otherwise `0`. This is a build flag, not a server authority. |

Production AI uses a Redis atomic reserve on
`lyo:classroom:continuous_teaching:production:pilot_reserved_microusd`.
The key has **no TTL** and may not be reset, deleted or refunded to bypass the
pilot total cap. The staging $60 ledger remains separate and untouched.
If Redis, provider pricing, provider health, or the approval gates fail,
the conversation uses the local ungraded acknowledgement; no paid AI call is made.

Never expose learner IDs, credentials, tokens, signed socket URLs, or lesson
content in deployment logs or artifacts.

## Production hosting verified in Railway (observed November 18, 2026)

This replaces the former assumption that LYO production infrastructure was
not discoverable. The live hosts are **not** in the project named
`LyoOne-Journey-Staging`:

| Domain | Railway project / environment | Service | Observed live `main` SHA |
| --- | --- | --- | --- |
| `https://api.lyoai.app` | `caring-cat` / `Lyo` | `LyoBackendJune` | `57c632f01bb8` |
| `https://lyoai.app` | `caring-cat` / `Lyo` | `LyoWeb` | `b8ee0bff5778` |
| `https://www.lyoai.app` | `zonal-wisdom` / `production` | `Lyo_Da_One` | `b8ee0bff5778` |

The first two services reported **online** with successful deployments and
no active critical/warning notifications. The `www` service also reported
online; however its environment had an **older staged Railway patch** not
applied to the live instance. Reconcile that patch before modifying this
environment. Other project environments with names `production` include
failed/crashed backend copies with *no canonical domain* and must **not** be
assumed to be the production release target.

**Rollback baselines:** retain and verify the above live deployment IDs and
SHAs immediately before any release. Do not assume these dated observations
remain current. Protect all three canonical domains and coordinate Web
deployment of both services with API compatibility. Set server feature
`LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED=0` before or during every
rollback; retain all Redis reservations. Do not auto-deploy any pending
Railway environment patch.

The source branches are still hundreds of commits ahead of production
(`Lyo_Da_One` release branch 258+ commits and backend 78+ versus `main`).
**No bulk merge or branch-to-production source switch is authorized by this
discovery.** Either reconcile and independently approve the complete
dependencies or create a focused, compatible cherry-picked release candidate.

## Release gate — do not merge or enable until ALL pass

1. **Source review**: independent reviewer approves backend, Web and Android
   diffs; review the very large ancestor branch diff versus `main` separately.
   Feature branches have substantial unreleased Classroom/staging changes and
   must not be bulk-merged to `main` without their own product-level signoff.
2. **CI**: production opt-in/allowlist/Redis reservation safety tests; complete
   backend regressions; Web unit tests, typecheck, production build; Android
   unsigned release compilation with the feature both OFF and ON.
3. **Real integration**: authorized synthetic-account startup, reply and
   transition at matching release SHAs, server-side session-ID isolation,
   exact-scene resume, and successful account deletion. No grades, mastery,
   transcript corruption or duplicate lesson advancement.
4. **Performance sample**: at least 20 starts and 10 transitions. Capture
   first visible teacher text, first audible teacher response, full scene,
   follow-up response, p50/p95, provider unavailable rate, and recovery.
   Suggested launch SLOs: first visible bridge text p95 <=1 second, first audible
   teacher speech p95 <=2 seconds where speech is enabled. Full lesson generation
   is independently tracked (was 21.5–24.75 seconds in prior isolated preview).
5. **Physical Android phone**: 20 audible turns, five interrupts/barge-ins,
   English and Spanish, stable teacher identity, audio not overlapping during
   the first real scene, session resumption and correct mic permissions.
   Check physical-device startup and transition p50/p95.
6. **Production target & rollback**: canonical Railway services are identified
   in the table above. Still confirm live SHAs, deployment authority, health,
   unresolved `www` staged patch, rollback target and accountable approver
   immediately before release. Verify signed Android publication separately.
7. **Paid-provider approval**: confirm currently valid Gemini model ID,
   actual published prices, expected demand, spending ceiling and persistent
   Redis budget key. Do not set rate approval flag on unsupported estimates.

## Official Gemini pricing reference (verified November 18, 2026)

Google's official [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
lists **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`) on the
standard paid tier at **$0.30 / 1 million input tokens** and
**$2.50 / 1 million output tokens** (including thinking tokens).

The code's approved-model *reservation upper bounds* are **$4 / 1 million
input** and **$20 / 1 million output**. These are deliberately more
conservative than the listed standard rates, but are not a supplier invoice,
an account-specific quota guarantee, or confirmation that a production
billing account/provider key is authorized. Recheck at the actual production
cutover, especially for priority, alternate routing, or future pricing.
The production `LYO_CONTINUOUS_TEACHING_PRODUCTION_RATES_APPROVED`
flag must remain **0** until a separate human approval reviews this
evidence and confirms the API account, exact model and spending cap.

## Safe activation sequence after all release gates pass

1. Build/publish the validated release candidate with client build flags OFF.
   Confirm no change in existing learner behavior; keep backend kill switch OFF.
2. Identify an approved synthetic production user ID. Set only that ID in the
   production allowlist. Enable backend and corresponding Web/Android client
   opt-in, initially with production AI disabled; verify only that user sees the
   text bridge and all other users are denied.
3. Once human-approved price/model/budget gates pass, explicitly enable the
   production AI budget for that canary; verify genuine Gemini follow-up,
   no double grading and no audio overlap.
4. Expand **only by adding approved users** after monitoring latency, error
   rate, provider spend and all test evidence. Never interpret the client
   query parameter as enrollment or authorization.

## Rollback / kill switches

Immediate backend rollback: set
`LYO_CONTINUOUS_TEACHING_PRODUCTION_ENABLED=0` without deleting any other
settings. This disables all new bridge sessions, regardless of client build.
To stop paid calls while retaining local bridge prompts, set
`LYO_CONTINUOUS_TEACHING_PRODUCTION_AI_ENABLED=0`.
For Web, rebuild/redeploy with
`NEXT_PUBLIC_LYO_CONTINUOUS_TEACHING_PRODUCTION=0`. For Android, ship the
previous approved Play artifact or a signed update with its release opt-in
disabled. Keep the ledger key and all prior paid reservations intact.

## Current disposition (November 2026)

Isolated preview startup and transition text are measured at 129–214ms and
65–99ms, respectively; Gemini follow-up and Web handoff were verified with
synthetic accounts. The underlying first full scene took 21.5–24.75 seconds.
**Physical-device voice QA, independent signoff, safe merge/deployment mapping,
signed Android publication and production billing authorization remain open.**
Production default OFF; no bulk merge, domain switchover, or Play publication.
