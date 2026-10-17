# PR #145 artifact recovery release gate

Keep the PR draft until the exact candidate is verified on isolated staging.
Production `api.lyoai.app` follows `main` independently of the Actions result;
merging may deploy immediately. Baseline observed on October 16, 2026:
`17d1695cc4994eeefebf27332e2bbc7d7c03eb15`.

## Implemented safety boundaries

- Disabled artifact storage raises a dedicated error. Creation/update cannot
  return a pretend saved artifact. Chat gives a completed, honest retry response.
- Missing/foreign/unowned update targets retain indistinguishable reopen/new-set
  recovery. Authentication and ownership precede mutation-model access and writes.
- Artifact plans defer text/voice confirmations until artifact operations finish.
- Flashcard updates satisfy the same nonempty card schema as new decks.
- Unexpected provider/storage exceptions retain error behavior. Interrupted
  generation remains incomplete, never an accepted completed artifact turn.

## Isolated live acceptance

`scripts/validate_artifact_recovery_staging.py` exercises real Chat HTTP/SSE,
the Firestore adapter, and durable assistant history. It does not mock providers
or storage. It seeds only synthetic artifact fixtures and removes only their
versions afterward. Synthetic account/conversation history remains for review.

Run from a trusted staging runtime with the same isolated Firestore credentials
as the deployed backend. Never copy production storage credentials into staging.
Requirements:

- A dedicated Railway staging backend pinned to the candidate; `/health` must
  report its full SHA, `environment=staging`, healthy database, enabled Firebase.
- An isolated Firebase project whose ID includes `staging`, `test`, or `sandbox`;
  the runtime's Firestore client project must match the explicitly approved ID.
- Two dedicated staging learner tokens in `LYO_ARTIFACT_STAGING_TOKEN_A` and `_B`.
- `ENVIRONMENT=staging`, `LYO_ARTIFACT_STAGING_READY=yes`, and
  `LYO_ARTIFACT_STAGING_FIREBASE_PROJECT` set to that isolated project ID.
- Working model-provider access on the backend and a compatible isolated SQL DB.

Start with the read-only preflight (replace placeholders with the deployed target):

```sh
python scripts/validate_artifact_recovery_staging.py \
  --url "$ARTIFACT_STAGING_URL" --expected-sha "$ARTIFACT_CANDIDATE_SHA" \
  --preflight-only --report artifacts/artifact-preflight.json
```

After preflight passes and the isolated prerequisites are configured, run the
same command without `--preflight-only`. Preflight success is not certification.

Acceptance requires all seven live cases: stale, foreign, unowned, no selected
artifact, unauthenticated update, owned versioned update/reload, new deck/reload.
For accepted turns the runner requires an explicitly completed answer, exactly
one terminal `[DONE]`, expected artifact count, persisted assistant text, and no
error/incomplete event. It verifies the deployed SHA again after the run.

Mutation-provider suppression, disabled storage, actual provider/write exceptions,
interrupted confirmations and incorrectly ordered plans are fault-injected in
the focused unit/SSE tests. These are separate evidence from live acceptance.
Physical client rendering and reconnect/device behavior still require client QA.

## October 16 staging limitation

Local verification: 61 focused artifact/storage/staging-gate/voice-lifecycle
tests passed. Six new safety cases failed against previous head `e4a144e` and
pass after the corrections. Fatal-error lint and whitespace checks passed.
The live read-only preflight refused the shared staging target because its
deployed revision did not match the candidate; no artifact matrix was run there.

The previously linked `LyoOne-Journey-Staging` backend is currently pinned to
password-reset PR #143, `66b141435c33079f240f8dc6e82bdc5b49b4841c`, with Firebase
disabled. Its Coach/HTTP smoke is not artifact evidence. Do not repurpose that
active validation service or accept its healthy status as a pass for this PR.
Provision/configure an isolated artifact target before the live matrix.

## Before merge or deployment

1. Attach focused test results and full CI for the final PR head.
2. Attach live report with identical expected/before/after SHAs, all seven cases
   passing, plus the actual Railway deployment ID and isolated Firebase project.
3. Review the final code and any remaining findings. Confirm repository release
   controls and rollback to the recorded production baseline before merging.
4. Deploy backend before dependent clients and verify the serving revision plus
   authenticated artifact create/update/recovery after rollout.

Do not equate green unit CI, an HTTP 200, a preflight-only report, skipped image
checks, or a run on a different revision with release acceptance.
