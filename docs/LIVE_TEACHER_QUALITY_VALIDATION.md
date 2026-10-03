# Live Teacher-Quality Validation

## Purpose

The deterministic Learning OS test suite proves orchestration: policy selection,
remediation ladders, hint weighting, transfer, persistence, reconnect behavior,
and retention scheduling. It does **not** prove that live model-authored teaching
is good enough to keep a learner engaged.

`scripts/live_teacher_quality.py` is the black-box bridge between those two
questions. It talks only to the same deployed HTTP and WebSocket contracts used
by real clients, then records durable Learning OS analytics before and after the
session.

## Safety and measurement rules

1. Run against the authenticated learner API. Never place bearer tokens in
   source control, CLI arguments, screenshots, or report files. Supply
   `LYO_ACCESS_TOKEN` through the process environment.
2. HTTPS is mandatory by default. `--allow-http` exists only for local
   development.
3. Do not fake a seven-day retention interval by modifying production dates.
   Seed the learning episode now; run the review phase later when the item is
   genuinely due.
4. The harness may force a wrong answer only when the delivered client contract
   explicitly identifies an incorrect guided option. If the checkpoint
   withholds its answer key, the harness records the selection as unknown and
   does not claim that remediation was tested.
5. Structural pass/fail is automated. Pedagogical quality remains a separate
   review of the captured teacher output plus the durable outcome metrics.

## Seed run

```bash
export LYO_ACCESS_TOKEN="<test learner bearer token>"
export LYO_BASE_URL="https://api.lyoai.app"

python scripts/live_teacher_quality.py seed \
  --topic "comparing fractions"
```

The seed run attempts the complete live chain:

```text
Chat
  -> routing
  -> Teaching Policy
  -> authored teaching / Smart Blocks
  -> persisted conversation
  -> Classroom
  -> free-form interruption
  -> answer / resume
  -> hint
  -> forced wrong guided response when the client contract permits
  -> remediation
  -> corrected response
  -> transfer response
  -> disconnect / reconnect with the same session id
  -> durable Learning OS analytics
```

The JSON report is written under `artifacts/teacher-quality/` by default. It
contains no bearer token.

## Later retention run

When the learned concept is genuinely due for review:

```bash
export LYO_ACCESS_TOKEN="<same test learner bearer token>"

python scripts/live_teacher_quality.py review
```

The runner reads `/api/v1/lyo2/chat/reviews/due` and uses the first due concept.
You can target a known concept explicitly:

```bash
python scripts/live_teacher_quality.py review \
  --review-concept-id compare_fractions
```

A seven-day retention claim is valid only when the durable analytics report
contains a retention attempt whose gap is at least seven real days.

## What to compare

For each subject and learner profile, capture at least these measures from the
Learning OS analytics response:

- **Intervention outcome:** success rate by teaching action, instrument and
  target evidence type.
- **Misconception repair:** eligible remediation follow-ups, repairs, repair
  rate and median repair time.
- **Transfer:** total and unaided transfer success.
- **Hint dependency:** hinted versus hint-free success.
- **Retention:** 1-day, 7-day and 30-day retrieval success as those windows
  become available.
- **Cross-surface continuity:** Chat->Classroom and Classroom->Chat follow-up
  success compared with same-surface controls.
- **Learning efficiency:** evidence-rung gain per active response minute.
- **Model efficiency:** calls, tokens, model mix, cache hits, session attribution
  and tokens per successful session.

Do not optimize policy on tiny samples. The deterministic Teaching Policy stays
authoritative for launch until there is enough attributed outcome data to
compare interventions for equivalent learner states.

## Subject matrix

Use several domains because a teacher that works only for one content shape is
not a general learning product.

| Domain | Example objective | Useful transfer |
| --- | --- | --- |
| Mathematics | Compare fractions with unlike denominators | Equal ribbons cut into different numbers of pieces |
| Biology | Explain photosynthesis inputs/outputs | Predict what changes when light is reduced |
| Physics | Apply Newton's second law | Compare acceleration under changed force/mass |
| Language | Use Spanish preterite vs imperfect | Choose tense in a new narrative context |
| Business | Apply contribution-margin reasoning | Evaluate a changed price/cost scenario |

Within each domain, run learner behaviors matching the deterministic simulation
suite: advanced, beginner, confident-but-wrong, quiet/partial, curious,
struggling, fast learner, and interrupter.

## Human teacher-quality rubric

The report tells us whether the system behaved correctly and whether learning
evidence improved. A reviewer should separately inspect the actual teacher
turns for:

- whether the explanation directly addresses the learner's words;
- whether examples are concrete and progressively demanding;
- whether a free-form detour is answered before the original lesson resumes;
- whether remediation targets the misconception instead of restating the same
  explanation;
- whether hints preserve productive struggle rather than reveal the answer;
- whether the transfer task is genuinely novel;
- whether the teacher avoids monologues, repeated questions and unnecessary
  praise;
- whether visual remediation adds information rather than decoration.

Those judgments should be stored as annotations beside the run, not written back
as mastery evidence.
