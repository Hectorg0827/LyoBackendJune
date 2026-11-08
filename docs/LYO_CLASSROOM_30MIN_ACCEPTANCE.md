# LYO staging classroom — 30-minute live acceptance

This gate requires **one observed, continuously active 30-minute browser session**.
Scripted backend tests, HTTP 200s, an open tab, and a 30-minute idle wait do not
substitute for real learner interactions. Run **staging only** using a dedicated
test learner. Do not enable paid voice providers or change production settings.

## Setup and evidence

- Record exact staging web URL, backend deployment/commit, classroom runtime,
  browser and test-learner alias. Never record credentials, tokens or real
  learner information in the test log.
- Start a 30-minute clock just before clicking **Enter Classroom**. Log time to
  first *audible* teacher speech as heard in the browser, separately from TTS
  first-byte/network timing. Do not infer audible timing from HTTP logs.
- Capture screenshots at the numbered checkpoints below, plus a redacted
  browser/network error snapshot after any failure. Audio quality needs a human
  listening verdict; a playable MP3 or successful fetch is insufficient.
- Log each activity using `scripts/classroom_30min_acceptance_log.py`; place the
  report in a temporary staging QA directory, never in source control.
- The test is **not passed** if authentication, voice permissions, missing
  teacher audio or a fatal classroom error prevent continuous interaction.

## Time-boxed interaction matrix

| Elapsed | Learner action | Required observable result | Evidence |
| --- | --- | --- | --- |
| 00:00–03:00 | Start **Teach me fractions**, 30-minute lesson. | New classroom opens; visible goal; first teacher speech measured; no overlapping board/CTA. | Screenshot 1: first board; start and first-audio times. |
| 03:00–07:00 | Advance each orientation/model beat using Next. | Complete worked example precedes a graded question; teacher text accompanies audible narration; teacher/mascot show only when useful, freeing board space. | Screenshot 2: worked example; count teacher entrances/exits and text overlap. |
| 07:00–12:00 | Answer first guided check correctly (e.g., `1/2 is larger than 1/3` when asked). | Specific explanation grounded in actual prompt; correct guided answer does not instantly claim mastery; no answer key is leaked beforehand. | Screenshot 3: feedback and progress. |
| 12:00–17:00 | Deliberately give an incorrect **new** response on another check (e.g., `1/4 > 1/3` when comparing those fractions). | Learner response remains visible; feedback explains the mistake; a different worked example or prerequisite appears; no punitive/false mastery. | Screenshot 4: wrong-answer feedback + remediation. |
| 17:00–21:00 | Request help; then give a partial/free-text answer such as `I think thirds are bigger` without the full requested reasoning. | Help preserves active question; teacher gives one helpful next step, not a leaked answer; partial answer triggers a relevant follow-up rather than keyword/length grading. | Screenshot 5: pending task, help and follow-up. |
| 21:00–25:00 | Solve a fresh faded/independent application **without help**. | Application is unseen, aligned with taught skill, graded semantically; only earned practice appears, not proof of long-term mastery. | Screenshot 6: unseen task and grade. |
| 25:00–27:00 | Navigate Previous/Next/Next Step; try a rapid duplicate click safely; skip or review a skill. | Controls do not overlap system UI; no accidental double advancement, duplicate grades or lost question; skip remains neutral. | Screenshot 7: navigation/progress. |
| 27:00–30:00 | Refresh/reconnect; continue the saved lesson; ask one last teacher question and reach recap if available. | Same scene/question resumes; answer is not regraded on refresh; teacher audio recovers or shows clear fallback; recap describes practice accurately. | Screenshot 8: resumed scene and final status; elapsed time >= 30 min. |

If the lesson completes early, start another classroom topic and keep interacting
until the elapsed session clock reaches 30 minutes. Mark any unvisited sequence
as **not tested**, never as passed. To test Spanish audio, use a second Spanish
topic and log `first_audio_es`; accent/pauses need a human listener.

## Measurable acceptance criteria

1. **Availability:** 30 minutes of active browser use, no fatal session error or
   unrecoverable blank screen; log all HTTP 5xx, 429, 502/504 and retry prompts.
2. **Speech:** first-audible latency, after-answer teacher-start latency and
   longest silent gap on at least five turns. Record voice consistency,
   pronunciation, pauses and unintended duplicate narration. Target first
   audible speech <= 2.5 seconds on a warmed single session, and no silent
   wait > 5 seconds without a visible recovery/working state; report misses.
3. **Instruction:** orientation -> modeled example -> guided -> faded -> fresh
   independent application -> recap. No answer leakage or premature mastery.
4. **Grading:** at least one correct, incorrect and partial response with
   specific evidence-grounded feedback; no invented student reasoning.
5. **State:** reconnect preserves the scene, draft limitations are transparent,
   and retry does not duplicate grade/evidence.
6. **Interaction:** responsive Next/Previous/Next Step; no overlapping controls,
   unusable dropdowns, persistent oversized mascots or audio/text mismatch.
7. **Fallback:** teacher voice failure, if observed or induced safely, displays
   a recoverable state or deliberately selected device voice. Do not assume
   fallback works from a successful MP3 alone.

**Verdict:** PASS only after the 30-minute active session is witnessed, all
required checkpoints are observed, no blocking errors occur, and human
listening quality is acceptable. Otherwise record **PARTIAL/BLOCKED/FAIL**
with exact elapsed duration and observed gaps.

## Logger examples

```bash
python scripts/classroom_30min_acceptance_log.py start \
  --output /tmp/lyo-classroom-30min.jsonl \
  --topic fractions --tester staging-qa

python scripts/classroom_30min_acceptance_log.py event \
  --output /tmp/lyo-classroom-30min.jsonl \
  --kind first_audio_en --status pass --latency-ms 1750 \
  --evidence screenshot-1

python scripts/classroom_30min_acceptance_log.py event \
  --output /tmp/lyo-classroom-30min.jsonl \
  --kind guided_wrong --status pass --evidence screenshot-4

python scripts/classroom_30min_acceptance_log.py finish \
  --output /tmp/lyo-classroom-30min.jsonl
```

`finish` reports the real elapsed clock and missing checkpoints. A short run
cannot pass merely because `finish` was called.
