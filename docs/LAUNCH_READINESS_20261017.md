# Combined launch candidate — 17 October 2026

This candidate integrates current main (including artifact recovery PR145 and the existing interactive fraction/board fallbacks) with backend PRs 130, 136, 139–144. It is a staging candidate, not a production certification.

## Acceptance ledger

| Area | Implemented in this candidate | Remaining evidence before public release |
| --- | --- | --- |
| 1. Artifacts and flashcards | Durable-storage failures and ownership recovery from current main; seven-case real-storage runner retained | Dedicated test Firebase project/credentials, two synthetic learners, all seven real provider/storage cases and reload checks |
| 2. Classroom and Coach | Canonical goal/exam/session handoffs and provider/timeout fixes from PR136; teaching-integrity runner from PR144 | Provider-backed scenarios, escalation/reteaching, saved recovery, duplicate-answer checks; 3 consecutive 4/4 misconception runs and human teaching review |
| 3. Courses | Atomic authenticated course/lesson persistence and private ownership from PR130; client companion in release branch | Exact staging pair: create, list saved, open every lesson, reload and foreign-owner denial |
| 4. Password recovery | Mounted request/confirm, one-hour password-bound links, credential epochs, refresh revocation, shared Redis throttle | Verified sender and actual delivered email; old password/access/refresh denial, expired/tampered/reused links and replica rate limits |
| 5. Security and progress | JWT/log containment, admin-only arbitrary XP, graded-event XP, persisted achievements; atomic ledger helpers and rollback; truthful course/time stats | PostgreSQL concurrency and authenticated profile readback on deployed pair; retained-log access/retention review |
| 6. Platforms | Companion client preserves web/iOS/Android contracts and first-frame socket authentication | Exact-revision CI, signed mobile builds, physical iOS/Android acceptance including mic interruption, background/resume and visual fallbacks |
| 7. Launch controls | Single migration head joins Coach and auth histories; upgrade rehearsal retains old learners/plans; public revision-pinned checks; Discover defaults off in client | Terms/privacy remain drafts needing owner factual/legal approval; deployed revision acceptance and release sign-off |

## Isolated infrastructure

Project: `LyoOne-Journey-Staging` (`8eb44c4c-d8df-46f2-b535-e75675823469`), environment `staging` (`423b2fa5-5771-4857-9de8-3d81ff0dad39`).

- `LyoLaunchBackend`: `da44a435-c4a6-447d-9c5a-84dc707099d1`
- `LyoLaunchWeb`: `702dc4b0-82ab-408e-ac8c-1cfea56e118b`
- Separate `LyoLaunchPostgres`: `bdc9b580-ebdf-4cf1-a273-6a25072f59f2`, 1 GiB persistent volume.
- Existing password-recovery staging services retain their current source and data.
- No production learner fixtures, Firestore writes or provider experiments are authorized by this document. Use the isolated project and synthetic accounts only.

## Release order

1. Require current-head backend CI and successful upgrade of an existing populated PostgreSQL schema.
2. Pin isolated backend to that tested SHA. Keep `CLASSROOM_STRICT_SCHEMA=0`. Configure a dedicated test Firebase project (its ID must contain `test`, `staging` or `sandbox`) and a verified test sender without copying production credentials.
3. Run existing artifact, HTTP, WebSocket, provider and teaching-integrity acceptance runners. Supply full expected commit SHAs. The staging target guard permits only the reserved journey services or the separate launch services, never arbitrary Railway apps or public production domains.
4. Pin companion client to its tested SHA; build with the isolated backend URL and journeys enabled only for staging. Run browser and real-device acceptance.
5. Obtain owner approval of the factual policy text. Keep Discover contained until its independent media gate passes.
6. Only after all gates pass: backend release first, then clients, then public acceptance bound to both deployed SHAs. A health HTTP200, deployment SUCCESS or passing unit tests alone cannot authorize completion of this ledger.


## Dedicated staging Firebase — required before the seven real artifact cases

The `LyoLaunchBackend` service is separate from the older `LyoJourneyStagingBackend` and production backend. A Firebase project configured for a different service does **not** configure Launch. As of this audit, neither isolated backend has `FIREBASE_PROJECT_ID` or a `FIREBASE_CREDENTIALS_JSON` / `FIREBASE_CREDENTIALS_PATH` variable; Launch reports Firebase disabled. Do not copy any existing production Firebase service-account key.

1. Create or select a **dedicated non-production** Firebase/Google Cloud project with `test`, `staging` or `sandbox` as a whole hyphen-separated component of its project ID. Enable **Cloud Firestore** (Native mode), using synthetic records only.
2. Create a dedicated service account **in that same test project** with only the Firestore permissions needed for the artifact test. Issue its key only if required by Railway's available secure credential mechanisms; never commit JSON or paste it into PR comments or CI logs. Store it privately as `FIREBASE_CREDENTIALS_JSON` on the **Launch staging backend only** (or mount it as a protected file and set `FIREBASE_CREDENTIALS_PATH`).
3. Set `FIREBASE_PROJECT_ID` to the exact test project ID. If using `GCP_PROJECT_ID`, it must equal the same ID. The staging adapter refuses Application Default Credentials, mismatched service-account projects, a project without the test/staging/sandbox marker, and a Firebase Admin app already initialized against another project.
4. After a **staging-only** redeployment, require `/health` to show the **expected 40-character deployed SHA**, `environment=staging`, healthy SQL database and `services.firebase=enabled`. `enabled` alone does not prove permissions or Firestore persistence.
5. From a trusted runtime with the **same test Firestore credentials**, set `ENVIRONMENT=staging`, `LYO_ARTIFACT_STAGING_FIREBASE_PROJECT`, `LYO_ARTIFACT_STAGING_TOKEN_A`, `LYO_ARTIFACT_STAGING_TOKEN_B` (two distinct synthetic learners), and `LYO_ARTIFACT_STAGING_READY=yes`. Run the runner in `--preflight-only` mode first, then full seven-case acceptance against `https://lyolaunchbackend-staging.up.railway.app`, passing its exact served SHA. Preserve the redacted report and deployed SHA. Do not set or log tokens in public CI steps.
6. Require stale/foreign/unowned/no-selection/unauthenticated recovery plus owned update/reload and new-deck/reload, including SSE completeness and history consistency. If Firestore asks for a composite index, create it **only in the test project** and rerun; do not relax fail-closed semantics.

The Lyo backend contains `scripts/validate_artifact_recovery_staging.py` and `tests/test_firebase_staging_isolation.py`. These are staging safety controls, not production launch approval. Without a distinct test-project credential, keep this acceptance gate **BLOCKED** and do not attempt production Firebase writes.
