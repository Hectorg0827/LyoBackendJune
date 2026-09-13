# Adaptive Classroom

The live SDUI classroom now runs through `AdaptiveTeacher` and `AdaptiveSession`,
called by `SceneLifecycleEngine.process_trigger`. The legacy director/compiler
helpers remain importable for compatibility; their fixed recognition → generic
written response → completion sequence is no longer the live teaching path.

## Learner experience

- A topic becomes a pathway of 3–6 specific skills. An authored lesson is divided
  into 2–4 skills grounded in its existing content. The selected time budget
  controls breadth; elapsed time never advances the learner.
- Each turn contains one short explanation, a concrete supporting example and
  one question. Predictions, choices, diagnosis, explanation and application
  use the existing question and text-input components.
- Every question supplies its actual scenario and asks a bounded task. Response
  instructions remain visible while typing. Typed answers and dictation remain
  available; a correct number or short sentence is valid.
- Partial answers receive one specific follow-up, with earlier reasoning visible
  and available to the evaluator. Wrong answers lead to another example and a
  smaller task. Uncertainty or a request for help is not a failed assessment.
- A skill needs two successful checks, including a fresh, unassisted application,
  before it is marked practised. Supported answers do not satisfy that independent
  check. The summary describes practice, not mastery or guaranteed retention.
- Skipping is neutral. Skipped skills remain pending and can be practised again.
  The next skill or authored lesson opens on an explicit Continue.

For example, a question can ask: “Two identical pizzas are cut into halves and
thirds. Which single piece is larger, and why?” If the learner answers “One half,”
the next question targets the missing reason; it does not demand a complete
rewrite or an unexplained keyword. Tasks are generated from the current skill,
teaching already shown, previous answers and the learner's requests.

## Evaluation and evidence

The server holds the active task, a private semantic rubric and a model answer.
It never trusts client correctness, a component belonging to another learner, or
an old answer delivered again. The evaluator accepts equivalent meanings and
checks only explicitly requested, taught criteria. It must cite actual learner
text for each satisfied criterion. Incomplete, inconsistent, low-confidence or
malformed evaluation cannot become an incorrect grade. An unclear question or
an over-demanding private rubric causes clarification instead.

AI generation uses the configured shared providers with bounded requests and
validated JSON. Invalid plans/turns get one repair attempt. If preparation fails,
the UI offers Retry and any available existing example. If evaluation fails,
the submitted answer is retained ungraded and Retry evaluates that same answer.
There is no invented fallback quiz or keyword-based passing score.

Graded evidence is queued in the saved session before it reaches the shared
learning-event stream. Checkpoint IDs deduplicate outbox replays. Recognition,
explanation and application stay distinct; support level damps confidence.
Legacy DKT receives supplied response timing only when present and valid.

## Persistence and routing

`ClassroomSession.context.guided_state` stores the plan, skill position, pending
question, partial answers, support, taught steps, consumed checkpoint IDs,
pending evidence and current scene. `guided_history` retains authored-lesson
states. Existing legacy progress/evidence fields are retained. No migration or
new provider credentials are required. Sessions without the new state build a
new pathway rather than inheriting the old two-question completion claim.

Every authenticated turn reloads durable state. Local locks serialize a learner's
requests within a worker; PostgreSQL advisory locks serialize them across
workers on an owned connection, released even on failure. Connection identity,
not action payload identity, selects the learner and session. Scene delivery is
restricted to that learner's connections even when other users choose the same
topic name. A save failure explicitly warns that the step has not synced and
does not emit grading evidence.

This persists submitted answers and the active teaching checkpoint. Unsubmitted
draft text and the exact audio playback position are not server checkpoints.
Guest sessions cannot promise durable cross-device resumption.

## Verification and rollout

Run the focused backend regression group:

```sh
python -m pytest \
  tests/test_adaptive_classroom.py \
  tests/test_adaptive_classroom_persistence.py \
  tests/test_ai_classroom_teaching_loop.py \
  tests/test_classroom_emits_evidence.py \
  tests/test_classroom_concept_identity.py \
  tests/test_hint_level_weighting.py \
  tests/test_classroom_safe_fallback.py \
  tests/test_client_cannot_declare_evidence.py \
  tests/test_evidence_ladder.py -q
```

Tests use scripted model responses; no live provider is called. Coverage includes
multi-skill progression, partial answers, numeric answers, paraphrase evidence,
invalid evaluations, provider failures, retries, duplicate submissions, skipped
practice, evidence deduplication, authenticated WebSocket routing, lock cleanup
and a real SQLite save/reload of an unfinished checkpoint. The older live-handler
tests have been migrated to drive this pathway instead of mocking it away.

Web validation uses `npm test` and `npm run build`. Existing Swift/Kotlin wire
models already carry `min_words` and the same SDUI component/action types; native
builds and device interaction have not been validated in this Linux workspace.

Before production acceptance, exercise a real English and Spanish topic with the
configured model, plus an authored lesson, on authenticated clients. Check a
paraphrase, partial answer, incorrect answer, help request, skip/review and a
reconnect from a second device. Exercise simultaneous submissions against the
production PostgreSQL configuration. Monitor latency, repeated retries and
question/rubric alignment. Offline contract tests do not establish model factual
accuracy, production latency, or actual learning gains; delayed retrieval with
real learners is needed to measure the latter.
