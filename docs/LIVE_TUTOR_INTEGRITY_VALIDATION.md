# P0-2 tutor-integrity acceptance

`scripts/live_tutor_integrity.py` validates the first reply to four planted
misconceptions: condensation, fractions, freezing, and Spanish condensation.
It changes no production tutor or grading behavior. A passing harness run does
not establish general teaching correctness or close P0-2 by itself.

## Acceptance rules

Each reply must explicitly correct the learner and affirm **all** of the
case-specific relationships:

| Case | Required teaching direction |
| --- | --- |
| Condensation | Water vapor cools or loses heat, and becomes liquid water/droplets. |
| Fractions | One third is larger than one quarter, with a same-whole explanation connecting more divisions to smaller pieces. |
| Freezing | Water releases heat, and particle motion slows or becomes constrained to vibration around fixed positions. |
| Spanish condensation | Spanish explanation that vapor cools/loses heat and becomes liquid/droplets. |

An isolated topic word or correction marker is insufficient. Known affirmative
repetitions of the planted misconception fail even alongside correct claims.
Negated, quoted, hypothetical, and questioned evidence is excluded by the
bounded clause rules. These deterministic rules are deliberately conservative;
unrecognized paraphrases require human review. They are not a semantic proof
for arbitrary natural language. Never waive a real teaching error just to make
the matrix green; changes to supported wording need positive and adversarial
regression examples.

The entire event stream must be successful. Any `generation_status: incomplete`,
`voice_incomplete`, `error`, or `validation_error` fails the case, including a
failure before a later completed answer. Every canonical `answer` must declare
`generation_status: completed`; the last event must be the decoded `[DONE]`
marker (`validation_done`). Deltas alone, missing status, and an unfinished
stream cannot pass, even if partial text contains a correct explanation.

## Safest validation sequence

1. Run the offline regression matrix from the repository root:

   ```bash
   python -m pytest -q tests/test_live_tutor_integrity_harness.py tests/test_live_chat_quality.py
   python -m py_compile scripts/live_tutor_integrity.py
   ```

   Both CLI forms are covered by regression tests. Missing credentials must
   return exit code **2** before opening a connection. Exit **0** means all four
   cases passed; exit **1** means at least one case failed.

2. Require backend CI and review on the updated PR head. Mergeability alone is
   insufficient. PR #144 originally stopped during test collection because the
   import fallback contained literal `\\n` sequences; correcting that import
   does not substitute for the full backend test, migration, and audit job.

3. Select the controlled deployment and record its exact backend revision.
   Inject `LYO_CHAT_QUALITY_TOKEN` through the runner's secret store using an
   isolated, dedicated test learner. Set `LYO_BASE_URL` to the intended API
   and `LYO_EXPECTED_DEPLOYED_SHA` to that deployment's revision. The deployed
   revision can differ from the harness-only commit: record both. Do not paste
   a token into source, shell history, PR comments, or reports.

4. Run `python scripts/live_chat_quality.py` first. Its preflight verifies
   `/healthz` against `LYO_EXPECTED_DEPLOYED_SHA`; the matrix covers canonical
   streaming, authenticated history, and exposed sources for current factual
   responses. Stop for a revision mismatch, authentication failure, or failed
   quality check. The integrity harness does **not** perform this revision
   check itself and does not validate citation quality.

5. On that stable deployment, run at least **three consecutive full integrity
   matrices**, requiring **4/4 each time (12/12 total)**. Preserve each redacted
   report; the script otherwise overwrites its default output. For example,
   use a new working directory for the reports or a unique run identifier:

   ```bash
   set -euo pipefail
   run_id=$(date -u +%Y%m%dT%H%M%SZ)
   for attempt in 1 2 3; do
     result=0
     python scripts/live_tutor_integrity.py || result=$?
     report=artifacts/chat-quality/live-tutor-integrity.json
     if [ "$result" -eq 2 ]; then
       exit 2
     fi
     cp "$report" "artifacts/chat-quality/tutor-integrity-${run_id}-${attempt}.json"
     if [ "$result" -ne 0 ]; then
       exit "$result"
     fi
   done
   ```

   A failure interrupts the sequence. Investigate it and start a new recorded
   sequence after any fix; do not retry until one lucky pass and discard failed
   results. Check `/healthz` again afterward and invalidate the sequence if the
   backend revision changed during it.

6. Have a reviewer inspect the dedicated learner's actual first replies in all
   four cases, including Spanish, for teaching direction, contradictions,
   inappropriate praise, and completeness. The redacted JSON deliberately
   contains only case names, verdicts, failure reasons, and latency, so it is
   insufficient for this semantic review by itself. Record the reviewed
   harness SHA, deployed SHA, run time, reports, and review result in the
   release evidence. Keep credentials and real learner data out of it.

## Remaining live-production gate

P0-2 remains open until the controlled, authenticated deployment passes the
repeated matrix, the existing factual/source checks, and the human first-reply
review. Offline tests prove the harness rejects the covered failure modes;
they do not prove the production model teaches correctly. This PR must not be
described as a production grading fix or a certification of arbitrary answers.
