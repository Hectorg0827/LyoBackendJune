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

## Recommended production run: GitHub Actions

For repeatable production checks, use the manual **Live teacher-quality
validation** workflow in GitHub Actions rather than copying a bearer token into
a terminal history.

Before the first run, create an Actions secret named
`LYO_TEACHER_QUALITY_TOKEN`. It should belong to a dedicated test learner,
not a staff/admin account and not a real learner. The workflow fixes the target
to `https://api.lyoai.app`, supplies the token only through the process
environment, runs the harness safety tests first, and uploads the redacted JSON
report as a 30-day artifact.

Run **seed** first. The Actions workflow now exposes named, coherent subject
presets and learner-behavior profiles. Each subject preset carries a matching
Chat prompt, free-form question, explanation answer, transfer answer, and
objective; the workflow never mixes a biology prompt with a math transfer task.

Available subject scenarios:
- `math_fractions`
- `biology_photosynthesis`
- `physics_newton2`
- `spanish_past_tense`
- `business_contribution_margin`

Available learner profiles:
- `advanced`
- `beginner`
- `confident_wrong`
- `quiet_partial`
- `curious`
- `struggling`
- `fast_learner`
- `interrupter`

The runner records both names at the top level of every report. A requested
wrong-answer behavior is only claimed when the live QuizCard explicitly marks
an option incorrect. If the key is withheld, the report records that the
behavior could not be forced instead of inventing a result.

Run **review** later, only after the server reports a concept as genuinely due.
An explicit review concept ID is treated only as a filter over the live due
queue; it cannot force an early or stale concept into retention mode. Do not
schedule review early just to obtain a retention number.

## Seed run

```bash
export LYO_ACCESS_TOKEN="<test learner bearer token>"
export LYO_BASE_URL="https://api.lyoai.app"

python scripts/live_teacher_quality.py seed \
  --scenario math_fractions \
  --profile interrupter
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
contains no bearer token. It also records whether free-response checkpoints
were explanation, application, transfer, or retrieval evidence, and whether a
remediation scene included a structured teaching visual. Those fields let later
analysis compare visual remediation with verbal-only remediation without
guessing from the transcript.

## Later retention run

When the learned concept is genuinely due for review:

```bash
export LYO_ACCESS_TOKEN="<same test learner bearer token>"

python scripts/live_teacher_quality.py review
```

The runner reads `/api/v1/lyo2/chat/reviews/due` and uses the first due concept.
You can target a known concept explicitly, but it will run only if that exact
concept is present in the server's current due queue:

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

Within each domain, run the matching named learner profiles from the workflow:
advanced, beginner, confident_wrong, quiet_partial, curious, struggling,
fast_learner, and interrupter. Do not treat repeated runs on the same dedicated
test learner as independent learners; persistent evidence is intentionally part
of the product. For clean between-profile comparisons, use separate dedicated
test learner credentials or compare only states with equivalent prior evidence.

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
