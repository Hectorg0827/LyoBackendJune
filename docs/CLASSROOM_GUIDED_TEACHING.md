# Guided teaching contract

The default classroom teaches before it assesses. One server-owned sequence is
shared by web, iOS and Android, with the same pedagogical state in audio and silent modes.

1. **Orient:** a relevant situation, an achievable goal and an invitation to begin.
2. **Model:** one complete worked example across 2–4 learner-paced beats. No graded question is attached.
3. **Guide:** model the setup and ask for one supported decision with 2–4 choices.
4. **Fade support:** leave most of a related example complete and ask for one missing step or result.
5. **Apply:** after the component skills have been practised with fading support, ask for a concise answer to a fresh, aligned problem.
6. **Recap:** show the reusable method and what was practised; invite a fresh example in a later session.

Time budgets reduce scope rather than remove guided practice. They never act as a countdown.
Consecutive choice tasks are allowed. Cognitive task type and answer format are independent.
Typing and dictation remain available; open answers are never graded by word count or keyword matching.

## Support and readiness

Each unit has 1–3 specific practice targets. A target needs guided practice and a
successful faded attempt without additional help before independent practice is
offered. This is a product scaffold, not an individual “80% mastery” threshold.
A correct guided answer does not complete a unit. An independent, unassisted
application is required for completion, and completion is labelled practice rather
than proof of long-term mastery.

Help preserves the question or paused demonstration. A partial response retains
the learner's reasoning and asks a specific follow-up. After extra help, a fresh
faded attempt is required. An incorrect answer triggers a different worked example;
repeated difficulty triggers prerequisite teaching. The primary teacher owns these
detours and returns to the original objective. A peer is never automatically shown
as a substitute teacher. Learners can explicitly request a challenge or review.
Skipping and asking for help are neutral; uncertain grading records no failure.

## Teaching activities

`LessonBlock(block_type="teaching_visual")` carries a validated fraction bar,
comparison, sequence or parameterised graph. A caption directs exploration and a
description provides a textual equivalent on clients without the renderer. Graph
axes remain fixed so changing parameters actually changes the displayed relationship.

`update_activity` sends `answer_data.value` (an integer) or the complete bounded
`answer_data.params` map. Its component ID is `visual:<current beat or checkpoint ID>`.
An activity update saves into the same session context, never grades an answer,
advances teaching, creates an assessment interaction or replays narration. Clients
coalesce slider updates and flush them before another action or disconnect.

## Resumption and compatibility

Version 2 guided state persists the presentation batch, beat index, current target,
guided/faded coverage, suspended example, pending question and visual values. The
existing learner-owned session context and evidence outbox remain the persistence
mechanism; no schema migration or parallel teaching backend is required.

Re-entry restores the saved scene without generating content or grading again.
Updated clients send actual CTA IDs; duplicate taps cannot skip teaching beats.
Legacy static Continue IDs remain accepted for installed clients and cannot provide
the same duplicate-tap guarantee. A version 1 pending question is restored verbatim;
legacy success counters do not count as new readiness evidence.

Save failures show an explicit unsynced state. Resumption on another device requires
successful server persistence; an unsent offline interaction cannot be guaranteed.

## Validation and learning outcomes

`test_guided_teaching_sequence.py` covers paced teaching, help detours, target coverage,
fading support, migration and non-grading visual updates. Persistence tests exercise
real database round trips. `tests.export_guided_fixtures` exports deterministic
production-runner payloads for all three client test suites.

Practice events record phase, target, response format, support and verdict. Existing
evidence recording receives grading events with hint provenance, never visual movement.
Software contracts establish behavior. Actual learning gains still require learner
evaluation: guided success without extra help, fresh application, delayed retrieval,
help usage and abandonment by phase. Do not present engagement or completion as retention.
