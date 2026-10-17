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
