"""One server-owned teaching sequence for audio, silent, web and native clients."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from lyo_app.ai.lesson_composer import slugify_skill
from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, Evaluation, GuidedState, LearningTurn, PendingTask, TeachingUnavailable,
    classroom_ceiling_comparisons, classroom_diagnostics, classroom_teaching_turns,
    classroom_unit_outcomes, normalize_text, requests_help, validation_summary,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, CTAButton, ExampleBlock, InputField, LessonBlock, ProgressBar, QuizCard,
    QuizOption, Scene, SceneType, TeacherMessage,
)
from lyo_app.ai_classroom.teaching_prompt import MOVES

logger = logging.getLogger(__name__)


class AdaptiveSession:
    def __init__(self, teacher: AdaptiveTeacher, skill_resolver=None):
        self.teacher = teacher
        self.skill_resolver = skill_resolver

    @staticmethod
    def record_concept(context, state: GuidedState) -> str | None:
        """Keep the question, evidence and review on the same saved skill ID."""
        if state.identity_required:
            if state.record_scope == "topic":
                return state.topic_skill_id
            index = state.active_review_index
            index = index if index is not None else state.unit_index
            return state.skill_ids[index] if index < len(state.skill_ids) else None
        if state.record_scope == "unit":
            index = state.active_review_index
            return state.plan.units[index].title if index is not None else state.unit.title
        return context.lesson_title or context.topic

    async def run(self, context, progress: dict[str, Any], trigger) -> Scene:
        data = trigger.action_data or {}
        intent = data.get("action_intent")
        raw = progress.get("guided_state")
        state = GuidedState.model_validate(raw) if raw else None
        if state and state.owner != context.user_id:
            raise ValueError("Guided session owner mismatch")
        if state is not None and self.skill_resolver is not None and not state.identity_required:
            try:
                identity = await self.skill_resolver(context, state.plan)
            except Exception as exc:
                logger.warning("Could not resolve saved classroom skills: %s", type(exc).__name__)
                return self.unavailable(context, state)
            state.skill_ids = identity.unit_ids
            state.topic_skill_id = identity.topic_id
            state.identity_required = True
            # Earlier servers could record every unit against one broad
            # lesson key. Keep historical events unchanged, but bind the
            # still-open question to the specific taught unit from now on.
            state.record_scope = "unit"
            if state.scene:
                # The question was already shown before the identity upgrade.
                # Rebind its public component to the same unit without changing
                # the question, answer key, or any historical outbox entry.
                concept_id = self.record_concept(context, state)
                for component in state.scene.get("components", []):
                    if component.get("type") in ("QuizCard", "InputField"):
                        component["concept_id"] = concept_id
                if state.record_scope == "unit":
                    indices = sorted(set([*state.completed, *state.skipped, state.unit_index]))
                    state.scene.setdefault("metadata", {})["target_concepts"] = [
                        state.skill_ids[i] for i in indices if i < len(state.skill_ids)
                    ]
            progress["guided_state"] = state.model_dump(mode="json")
        if state is None:
            if intent == ActionIntent.UPDATE_ACTIVITY:
                return self.unavailable(context, None)
            progress.setdefault(
                "record_scope", "unit" if data.get("record_scope") == "unit" else "topic"
            )
            try:
                plan = await self.teacher.plan(context)
            except TeachingUnavailable:
                return self.unavailable(context, None)
            identity = None
            if self.skill_resolver is not None:
                try:
                    identity = await self.skill_resolver(context, plan)
                except Exception as exc:
                    logger.warning("Could not resolve classroom skills: %s", type(exc).__name__)
                    return self.unavailable(context, None)
            challenge = context.classroom_mode.value in ("challenge", "review")
            state = GuidedState(
                owner=context.user_id, course_id=context.course_id,
                lesson_id=context.lesson_id, lesson_index=context.lesson_index,
                plan=plan, mode=context.classroom_mode.value,
                record_scope=("unit" if self.skill_resolver is not None or
                              (not context.lesson_title and progress["record_scope"] == "unit"
                               and len(plan.units) > 1) else "topic"),
                skill_ids=identity.unit_ids if identity else [],
                topic_skill_id=identity.topic_id if identity else None,
                identity_required=self.skill_resolver is not None,
                remaining_units=list(range(1, len(plan.units))),
                challenge_requested=challenge,
                phase="independent" if challenge else "diagnose",
                next_move="independent" if challenge else "diagnose",
            )
            if not challenge:
                self.open_unit(context, state)
            progress["course_complete"] = False
            progress["guided_state"] = state.model_dump()

        if data.get("welcome") and state.scene:
            # Reopening after an authoring outage must try the saved move
            # again, rather than replay an unusable Retry scene forever.
            retry_on_open = next((c for c in state.scene.get("components", [])
                                  if c.get("action_intent") == ActionIntent.RETRY), None)
            if retry_on_open is None:
                return Scene.model_validate(state.scene)
            intent = ActionIntent.RETRY
        if intent == ActionIntent.UPDATE_ACTIVITY:
            return self.update_activity(context, progress, state, trigger)
        if trigger.component_id in state.handled and state.scene:
            return Scene.model_validate(state.scene)
        retry_button = next((c for c in (state.scene or {}).get("components", [])
                             if c.get("action_intent") == ActionIntent.RETRY), None)
        recovering = intent == ActionIntent.RETRY and retry_button is not None
        if recovering:
            if trigger.component_id not in (None, retry_button["component_id"]):
                return self.current_or_retry(context, state)
            self.handled(state, retry_button["component_id"])
        state.mode = context.classroom_mode.value
        learner_input = str(data.get("message") or data.get("text") or data.get("question") or "")[:2000]
        if recovering:
            learner_input = state.generation_input

        if (state.unit_done or state.path_done) and intent in (
            ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE,
            ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE,
        ):
            self.reset_unit(state)
            self.open_unit(context, state)
            state.path_done = False
        if state.path_done and intent == ActionIntent.REQUEST_REVIEW:
            needs_support = bool(state.skipped)
            itinerary = sorted(set(state.skipped)) or list(range(len(state.plan.units)))
            state.unit_index, state.remaining_units = itinerary[0], itinerary[1:]
            self.reset_unit(state)
            state.path_done = False
            state.challenge_requested = not needs_support
            state.phase = state.next_move = "orient" if needs_support else "independent"
        elif state.path_done:
            return self.save(progress, state, self.summary(context, state))
        if state.unit_done:
            if intent != ActionIntent.CONTINUE:
                return self.save(progress, state, self.summary(context, state))
            if not self.current_continue(state, trigger):
                return self.current_or_retry(context, state)
            self.handled(state, state.step_id)
            state.unit_index = state.remaining_units.pop(0)
            self.reset_unit(state)
            self.open_unit(context, state)

        # Demonstrations are paced by explicit, identifiable Continue events.
        # Asking a question may interrupt them without throwing the example away.
        closing = False
        if state.presentation and intent == ActionIntent.CONTINUE:
            if not self.current_continue(state, trigger):
                return self.current_or_retry(context, state)
            self.handled(state, state.step_id)
            if state.beat_index + 1 < len(state.presentation.demonstration):
                state.beat_index += 1
                state.phase = "model"
                state.model_steps_seen += 1
                state.step_id = str(uuid4())
                self.remember_beat(state, self.current_beat(state))
                return self.save(progress, state, self.presentation_scene(context, state))
            state.presentation = None
            if state.paused_presentation:
                paused = state.paused_presentation
                state.presentation = LearningTurn.model_validate(paused["presentation"])
                state.beat_index, state.phase = paused["beat_index"], paused["phase"]
                state.paused_presentation = None
                state.step_id = str(uuid4())
                return self.save(progress, state, self.presentation_scene(context, state))
            if state.return_to_checkpoint and state.pending:
                state.return_to_checkpoint = False
                state.phase = state.pending.phase
                return self.save(progress, state, self.checkpoint(context, state))
            if state.next_move in ("reteach", "prerequisite") and state.support_attempts >= 2:
                # Teaching continues after supported remediation. Record what
                # needs another visit; do not turn repeated difficulty into a
                # pass-or-repeat gate or award unearned completion evidence.
                #
                # And do not end here. A learner who has just been wrong three
                # times leaves with a run of failures as the whole experience of
                # the skill, which is most of whether they come back. They get
                # one question at the level of the prerequisite just taught,
                # whatever they answer with, so the last thing that happens is
                # something they can do.
                if not state.closing_win_asked:
                    state.closing_win_asked = True
                    state.next_move = "closing_win"
                    state.phase = state.phase if state.phase in ("guided", "faded") else "guided"
                    state.last_feedback = self.copy(context,
                        "We've worked through the tricky step together. One more, on just that step.",
                        "Revisamos juntos el paso difícil. Una más, solo sobre ese paso.")
                    closing = True
                elif state.unit_index not in state.skipped and state.unit_index not in state.completed:
                    state.skipped.append(state.unit_index)
                if not closing:
                    # A skill the learner could not do today is the one most
                    # worth bringing back soonest, so it is scheduled as a
                    # failed recall rather than left out altogether.
                    self.schedule_review(context, state, passed=False)
                    self.event(state, "practise_later", phase=state.phase,
                               reason="continued_after_support")
                    state.last_feedback = self.copy(context,
                        "We've worked through the tricky step together. Let's keep learning and revisit this skill for more practice.",
                        "Revisamos juntos el paso difícil. Sigamos aprendiendo y volvamos a esta habilidad para practicarla más.")
                    self.finish_unit(state)
                    return self.save(progress, state, self.summary(context, state))
            elif not closing:
                state.phase = state.next_move = "guided"
        elif state.presentation and intent in (
            ActionIntent.SUBMIT_ANSWER, ActionIntent.SUBMIT_TRANSFER, ActionIntent.RETRY,
        ) and not recovering:
            return self.save(progress, state, self.presentation_scene(context, state))

        pending = state.pending
        move = state.next_move
        answer = data.get("answer_data") or {}
        submitting = intent in (ActionIntent.SUBMIT_ANSWER, ActionIntent.SUBMIT_TRANSFER)
        retry_evaluation = (
            (recovering or (
                intent == ActionIntent.CONTINUE and retry_button is not None
                and trigger.component_id in (
                    None, "continue", "web_continue", "android_continue",
                    retry_button["component_id"],
                )
            )) and pending is not None and pending.retry_response is not None
            and pending.task.response_format != "choice"
        )
        if submitting or retry_evaluation:
            if not pending or (not retry_evaluation and trigger.component_id != pending.id):
                return self.current_or_retry(context, state)
            choice = pending.task.response_format == "choice"
            if retry_evaluation:
                response = pending.retry_response
            elif choice:
                option = next((o for o in pending.task.options if o.id == answer.get("selected_option_id")), None)
                if intent != ActionIntent.SUBMIT_ANSWER or option is None:
                    return self.current_or_retry(context, state)
                response = option.label
            else:
                if intent != ActionIntent.SUBMIT_TRANSFER:
                    return self.current_or_retry(context, state)
                response = str(answer.get("response") or learner_input).strip()[:2000]
            if not response:
                return self.current_or_retry(context, state)
            if choice:
                result = Evaluation(
                    verdict="correct" if option.correct else "incorrect", confidence=1,
                    misconception=option.misconception if not option.correct else None,
                    question_clear=True, feedback=option.feedback if len(option.feedback.split()) >= 3 else self.copy(
                        context, "Let's work through that decision together.", "Revisemos juntos esa decisión."),
                )
            else:
                result = await self.teacher.evaluate(context, pending, response)
            pending.retry_response = None
            state.last_feedback = result.feedback
            if result.verdict == "unavailable":
                pending.retry_response = response
                return self.save(progress, state, self.unavailable(context, state))
            self.handled(state, pending.id)
            pending.answers = [*pending.answers, response][-5:]
            pending.attempts += 1
            pending.feedback = result.feedback
            self.event(state, "response", phase=pending.phase, target=pending.task.target_index,
                       verdict=result.verdict, extra_help=pending.extra_help_used,
                       response_format=pending.task.response_format, response=response,
                       feedback=result.feedback, misconception=result.misconception)
            if state.closing_win_asked and pending.phase != "diagnose":
                return self.save(progress, state,
                                 self.close_on_a_success(context, state, pending, result, data))
            if pending.phase == "diagnose":
                move = self.after_diagnostic(context, state, pending, result, response,
                                             response_time_ms=data.get("response_time_ms"),
                                             option=option if choice else None)
            elif pending.phase in ("transfer", "interleave") and result.verdict != "clarify":
                # Neither a transfer nor a revisit is a pass-or-repeat gate.
                # A partial answer is useful feedback, but proves neither rung.
                if result.verdict in ("correct", "incorrect"):
                    self.record_practice(context, state, pending, result, data)
                if pending.phase == "transfer":
                    self.finish_transfer(context, state)
                    return self.save(progress, state, self.summary(context, state))
                move = self.end_interleave(state)
            elif result.verdict == "partial" and pending.attempts < 3:
                # Needing a targeted follow-up on supported practice says the
                # same thing a wrong answer says about a ceiling that claims
                # independence, and this branch returns before the withdrawal
                # below. Without it, a learner who was partly right at guided
                # practice and then unaided at faded practice would carry the
                # tap's claim into every remaining component skill, while one
                # who was simply wrong and recovered the same way would not.
                self.withdraw_ceiling(state)
                pending.assisted = pending.extra_help_used = True
                pending.hints_used += 1
                pending.hint_level = pending.hint_level or "principle"
                pending.follow_up = result.follow_up
                pending.id = str(uuid4())
                return self.save(progress, state, self.checkpoint(context, state, follow_up=True))
            else:
                if result.verdict in ("correct", "incorrect"):
                    self.record_practice(context, state, pending, result, data)
                if result.verdict == "correct":
                    state.successes += 1
                    state.support_attempts = 0
                    self.confirm_ceiling(state, pending)
                    if self.after_success(state, pending):
                        state.pending = None
                        self.schedule_review(context, state, passed=True)
                        return self.save(progress, state, self.summary(context, state))
                    move = state.phase
                    # Their first success is the moment they have something to
                    # explain and have just been shown they can do it. The
                    # ladder keeps its place: `state.phase` is untouched, so
                    # the next move after this is where practice left off.
                    if not state.explained and not state.challenge_requested:
                        move = "explain"
                    elif self.start_interleave(context, state):
                        move = "interleave"
                elif result.verdict == "clarify":
                    # Ambiguous wording and requests for help are not failures.
                    move = "help" if requests_help(response) else "clarify"
                    state.return_to_checkpoint = requests_help(response)
                    pending.assisted = pending.extra_help_used = True
                    pending.hints_used += 1
                    if state.return_to_checkpoint:
                        pending.id = str(uuid4())
                elif pending.task.kind == "explain":
                    # Asked once, whatever they answer. An explanation is
                    # beside the ladder, so a shaky one cannot cost the
                    # learner their ceiling, a support attempt or their rung
                    # — and above all it must not stay unasked, or their next
                    # successful answer would ask again and a learner who can
                    # do the skill but cannot yet say why would go round that
                    # loop until repeated difficulty ended the unit on them.
                    # Reteaching is the whole response, and they step down a
                    # rung the way any reteach leaves a learner — supported,
                    # having just been shown it again — rather than by the
                    # failure path, which would take their standing with it.
                    state.explained = True
                    move = "reteach"
                    state.return_to_checkpoint = False
                else:
                    self.withdraw_ceiling(state)
                    state.support_attempts += 1
                    state.target_index = pending.task.target_index
                    state.faded_targets = [i for i in state.faded_targets if i != state.target_index]
                    move = "prerequisite" if state.support_attempts >= 2 else "reteach"
                    state.return_to_checkpoint = False
            learner_input = response

        elif intent == ActionIntent.SKIP_QUESTION:
            ungraded_button = next((c for c in (state.scene or {}).get("components", [])
                                    if c.get("action_intent") == ActionIntent.SKIP_QUESTION), None)
            continue_ungraded = (pending is not None and pending.retry_response is not None
                                 and ungraded_button is not None
                                 and trigger.component_id == ungraded_button["component_id"])
            if not pending or (trigger.component_id != pending.id and not continue_ungraded):
                return self.current_or_retry(context, state)
            self.handled(state, pending.id)
            if continue_ungraded:
                # A provider failure is not a learner skipping or failing a
                # question. Retire this ungraded checkpoint, keep every earlier
                # success, and offer a fresh question at the same rung.
                self.handled(state, ungraded_button["component_id"])
                self.event(state, "evaluation_unavailable", phase=pending.phase,
                           target=pending.task.target_index)
                pending.retry_response = None
                state.pending = None
                state.return_to_checkpoint = False
                state.last_feedback = self.copy(
                    context, "Your answer was saved but not graded. Let's try a fresh example.",
                    "Tu respuesta se guardó sin evaluar. Probemos un ejemplo nuevo.")
                if pending.phase == "transfer":
                    self.finish_transfer(context, state)
                    return self.save(progress, state, self.summary(context, state))
                if pending.phase == "interleave":
                    move = self.end_interleave(state)
                elif pending.phase == "diagnose":
                    state.diagnosed = True
                    state.phase = move = "orient"
                else:
                    state.phase = move = pending.phase
            elif pending.phase == "diagnose":
                # Passing on "can you already do this?" is itself an answer: no.
                # It must not mark the skill for later review the way skipping
                # practice does — the learner has asked to be taught it now.
                state.diagnosed = True
                state.return_to_checkpoint = False
                classroom_diagnostics.labels("skipped").inc()
                self.event(state, "diagnostic", phase="diagnose", verdict="declined",
                           target=pending.task.target_index)
                state.last_feedback = self.copy(
                    context, "No problem — let's build it from the start.",
                    "Sin problema: vamos a construirlo desde el principio.")
                state.phase = move = "orient"
            else:
                if pending.phase == "interleave":
                    move = self.end_interleave(state)
                elif pending.phase == "transfer":
                    self.finish_transfer(context, state)
                    return self.save(progress, state, self.summary(context, state))
                else:
                    if state.unit_index not in state.skipped and state.unit_index not in state.completed:
                        state.skipped.append(state.unit_index)
                    self.schedule_review(context, state, passed=False)
                    self.event(state, "practise_later", phase=state.phase)
                    state.pending = None
                    self.finish_unit(state)
                    state.last_feedback = self.copy(context, "You can return to this skill when you are ready.",
                                                    "Puedes volver a esta habilidad cuando estés listo.")
                    return self.save(progress, state, self.summary(context, state))
        elif intent in (ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE,
                        ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE):
            if state.presentation and not state.paused_presentation:
                state.paused_presentation = dict(presentation=state.presentation.model_dump(),
                                                beat_index=state.beat_index, phase=state.phase)
            asking_about_a_probe = (
                pending is not None and pending.phase == "diagnose"
                and intent in (ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE)
            )
            state.return_to_checkpoint = (
                pending is not None and pending.id not in state.handled
                and not asking_about_a_probe
            )
            if pending and not asking_about_a_probe:
                pending.assisted = pending.extra_help_used = True
                pending.hints_used += 1
                pending.hint_level = "full_example" if intent == ActionIntent.REQUEST_EXAMPLE else "worked_step"
            if asking_about_a_probe:
                # Hinting at a probe's answer destroys the only thing the probe
                # measures, and returning to it afterwards would grade the
                # learner on an answer we handed them. Wanting help here is
                # itself the finding: teach the skill.
                self.handled(state, pending.id)
                state.diagnosed = True
                classroom_diagnostics.labels("help").inc()
                self.event(state, "diagnostic", phase="diagnose", verdict="asked_for_help",
                           target=pending.task.target_index)
                state.phase = move = "orient"
            else:
                move = ("answer_question" if intent in (ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE)
                        else "reteach" if intent == ActionIntent.REQUEST_EXAMPLE else "help")
            self.event(state, "help", phase=state.phase, intent=str(intent))
        elif intent == ActionIntent.SKIP_AHEAD:
            # A learner explicitly asking for a challenge may demonstrate prior
            # knowledge. Normal practice can never take this shortcut.
            state.challenge_requested = True
            state.presentation = state.paused_presentation = None
            if pending:
                self.handled(state, pending.id)
            state.phase = move = "independent"
        elif state.presentation and not recovering:
            return self.save(progress, state, self.presentation_scene(context, state))
        elif pending and pending.id not in state.handled and not recovering:
            return self.save(progress, state, self.checkpoint(context, state))

        state.next_move = move
        state.generation_input = learner_input
        # Accepted answers and their outbox events belong to the learner even
        # when composing the next screen fails. Only install a new question
        # after it has successfully passed the actual rendering contract.
        before_generation = state.model_copy(deep=True)
        try:
            turn = await self.teacher.turn(context, state, move, learner_input)
            return self.accept_turn(context, progress, state, turn, move)
        except (TeachingUnavailable, ValidationError) as exc:
            logger.warning("Classroom step unavailable: move=%s cause=%s", move, validation_summary(exc))
            return self.save(progress, before_generation, self.unavailable(context, before_generation))

    def accept_turn(self, context, progress, state, turn, move):
        state.generation_input = ""
        self.remember_beat(state, turn)
        if turn.task is None:
            if not state.return_to_checkpoint:
                state.pending = None
            state.presentation = turn
            state.beat_index = -1
            state.step_id = str(uuid4())
            # A probe that somehow arrived without a question is an
            # orientation, not a modelling step: there is nothing to model yet.
            state.phase = "orient" if move in ("orient", "diagnose") else "model"
            scene = self.presentation_scene(context, state)
            classroom_teaching_turns.labels(move if move in MOVES else "other").inc()
            return self.save(progress, state, self.delivered(state, scene))

        state.presentation = None
        if move == "diagnose":
            # A probe is unsupported by definition — nothing has been taught
            # for it to lean on. Marking it assisted, as practice is, would
            # damp the confidence of the strongest demonstration this engine
            # can collect: the learner doing it before being shown how.
            phase, supported = "diagnose", False
        else:
            phase = state.phase if state.phase in ("guided", "faded", "independent", "transfer", "interleave") else "guided"
            supported = phase in ("guided", "faded")
        state.pending = PendingTask(
            task=turn.task, speech=turn.speech, board_title=turn.board_title,
            board_content=turn.board_content, visual=turn.visual, phase=phase,
            assisted=supported, hints_used=1 if supported else 0,
            hint_level="worked_step" if supported else None, taught_steps=state.taught_steps.copy(),
        )
        state.task_kinds = [*state.task_kinds, turn.task.kind][-8:]
        state.recent_questions = [*state.recent_questions, normalize_text(turn.task.scenario + " " + turn.task.question)][-12:]
        state.next_move = phase
        scene = self.checkpoint(context, state)
        classroom_teaching_turns.labels(move if move in MOVES else "other").inc()
        return self.save(progress, state, self.delivered(state, scene))

    @staticmethod
    def delivered(state, scene):
        """Retire a feedback line once the learner has actually been told it.

        `last_feedback` was written when the answer was graded and read by
        whichever screen came next, but nothing ever cleared it — so it was
        read again by the screen after that. A learner who tapped "I'm not sure
        yet" was told "let's build it from the start", sat through the whole
        worked example, and then met their first practice question with the
        same sentence on top of it. The line is right where it is said and
        wrong four screens later, when it describes a decision already acted
        on.

        The rendered scene keeps the text — it is saved with it, so a resume
        shows the learner what they were shown.
        """
        state.last_feedback = ""
        return scene

    def after_diagnostic(self, context, state, pending, result, response,
                         response_time_ms=None, option=None) -> str:
        """Decide where this unit actually starts, from what the learner just showed.

        A diagnostic is the one checkpoint a learner cannot fail. It is asked
        before anything is taught, so a wrong answer says only that the unit
        has work to do — which is what the unit is for. Nothing here increments
        `support_attempts`, marks the unit for review, or reteaches an answer
        the learner was never given: those all read a wrong answer as a
        setback, and this one is the starting line.

        The answer sets a ceiling — the furthest this unit may fast-forward to
        once real work confirms it — and the unit starts one rung *below* that
        ceiling. Four options cannot tell knowing something apart from picking
        it: a learner who has never met the skill lands on the right option
        once in four. So the rung below is where being wrong about the tap is
        cheap. It costs a learner who did know it one question they will get
        right, where starting above them drops someone into practice they
        cannot do, which is what makes an opening question feel like the test
        it was never meant to be.

        | What the learner did | Ceiling | Starts at |
        | --- | --- | --- |
        | Tapped the correct option | `independent` | guided practice |
        | Tapped a near miss | `faded` | the one step it turns on |
        | Tapped a fundamental misconception | `guided` | the full example, aimed at it |
        | Tapped "not sure yet" | none | the beginning |
        | Explained it correctly, unaided (saved session) | `independent` | faded practice |

        A correct tap and a correct explanation share a ceiling and not an
        entry point, because a tap has no reasoning behind it to start from:
        the explanation enters at faded practice as it always has, while the
        tap buys supported practice and skips the demonstration.

        The ceiling only ever lets the unit move faster than the ladder would;
        it cannot award a rung, complete a unit, or survive being contradicted
        by real work.

        Evidence is written only for a correct, unaided *open* answer, which
        reaches this method from sessions saved before the probe became a tap.
        The learner's own reasoning before instruction earns `explanation`,
        never `transfer`, which is defined relative to something taught. A tap
        earns nothing at all: recognising the right answer among four is not a
        claim worth keeping about anybody, and the record is for claims.

        An incorrect probe writes **no** evidence rather than a zero. "Measured
        at zero on a skill never taught" is a claim about the learner that the
        probe does not support, and the learner record keeps "not started"
        and "attempted and got nothing" apart deliberately.
        """
        state.diagnosed = True
        state.support_attempts = 0
        state.return_to_checkpoint = False
        unaided = not pending.assisted and not pending.extra_help_used
        declined = option is not None and option.abstains
        classroom_diagnostics.labels(
            "abstained" if declined else
            result.verdict if result.verdict in ("correct", "incorrect", "partial", "clarify")
            else "unavailable"
        ).inc()
        self.event(state, "diagnostic", phase="diagnose", target=pending.task.target_index,
                   verdict="declined" if declined else result.verdict, unaided=unaided,
                   response_format=pending.task.response_format, response=response,
                   misconception=None if declined else result.misconception)

        if declined:
            # Tapping "I'm not sure yet" is the same answer as passing on the
            # question, and it is the reason that option exists: a learner who
            # does not know should not have to guess to get taught.
            ceiling, entry = None, "orient"
            state.last_feedback = self.copy(
                context, "No problem — let's build it from the start.",
                "Sin problema: vamos a construirlo desde el principio.")
        elif result.verdict == "correct" and unaided and pending.task.response_format != "choice":
            # An open answer with its reasoning, from a session saved before
            # the probe became a tap. Performance before instruction is the
            # strongest thing this engine can record.
            ceiling, entry = "independent", "faded"
            state.outbox.append(dict(
                event_id=pending.id, user_id=context.user_id,
                concept_id=self.record_concept(context, state),
                correct=True, evidence_type="explanation",
                hints_used=0, hint_level=None, misconception=None,
                response_time_ms=response_time_ms,
            ))
            state.last_feedback = (result.feedback + " " + self.copy(
                context,
                "You already have this, so we won't sit through the basics.",
                "Ya dominas esto, así que no repasaremos lo básico.",
            )).strip()
        elif result.verdict == "correct":
            ceiling, entry = "independent", "guided"
            state.last_feedback = self.copy(
                context,
                "That's it. We'll skip the basics and pick this up in practice.",
                "Exacto. Nos saltamos lo básico y lo retomamos practicando.")
        elif option is not None and option.gap == "near_miss":
            ceiling, entry = "faded", "orient"
            state.last_feedback = self.copy(
                context,
                "You have most of this already. Let's look at the step it turns on.",
                "Ya tienes casi todo esto. Veamos el paso del que depende.")
        elif option is not None and option.gap == "fundamental":
            ceiling, entry = "guided", "orient"
            state.last_feedback = self.copy(
                context,
                "Thanks — that tells me where to start. Let's build it up together.",
                "Gracias: eso me dice dónde empezar. Vamos a construirlo juntos.")
        elif result.verdict == "partial":
            # An open answer with part of the skill in it, from a saved
            # session. Its own words are the place to build from, so the
            # evaluator's feedback stands and practice starts supported.
            ceiling, entry = "faded", "guided"
        else:
            # Wrong, unclear, or an option saved before distractors named the
            # gap they reveal: teach it, starting from what the learner said.
            # `orient` reaches the generator with their answer and this
            # feedback already in its payload.
            ceiling, entry = None, "orient"

        state.diagnostic_ceiling = ceiling
        state.ceiling_prediction = ceiling
        state.ceiling_source = "open" if pending.task.response_format != "choice" else "tap"
        state.diagnostic_misconception = "" if declined else (result.misconception or "")
        state.phase = entry
        return entry

    def close_on_a_success(self, context, state, pending, result, data):
        """End a hard unit on the closing question, whichever way it went.

        The unit is filed for more practice either way — repeated difficulty
        never awards completion, and this question is not a retake. What it
        changes is the last thing that happened to the learner: something at the
        level of the step just taught, and a teacher who says which part they
        got. Nothing here loops: one question was offered, and this is its end
        whatever the answer.
        """
        if result.verdict in ("correct", "incorrect"):
            state.outbox = [*state.outbox, dict(
                event_id=pending.id, user_id=context.user_id,
                concept_id=self.record_concept(context, state),
                correct=result.verdict == "correct",
                evidence_type=None if pending.task.response_format == "choice"
                else "application" if pending.task.kind == "apply" else "explanation",
                hints_used=pending.hints_used, hint_level=pending.hint_level,
                misconception=result.misconception if result.verdict == "incorrect" else None,
                response_time_ms=data.get("response_time_ms"),
            )]
        if state.unit_index not in state.skipped and state.unit_index not in state.completed:
            state.skipped.append(state.unit_index)
        self.schedule_review(context, state, passed=False)
        self.event(state, "practise_later", phase="closing_win",
                   reason="closed_on_a_success" if result.verdict == "correct" else "closed_after_support",
                   verdict=result.verdict)
        state.last_feedback = self.copy(
            context,
            "That's the step that was giving you trouble, and you just did it. "
            "We'll come back to the rest of this skill with more practice."
            if result.verdict == "correct" else
            "Thanks for working through that with me. We'll come back to this skill "
            "with more support — nothing here counts against you.",
            "Ese es el paso que te costaba, y acabas de hacerlo. "
            "Volveremos al resto de esta habilidad con más práctica."
            if result.verdict == "correct" else
            "Gracias por trabajarlo conmigo. Volveremos a esta habilidad con más "
            "apoyo; nada de esto cuenta en tu contra.")
        state.pending = None
        self.finish_unit(state)
        return self.summary(context, state)

    @staticmethod
    def compare_ceiling(state, observed: str, result: str) -> None:
        if state.ceiling_prediction is None or state.ceiling_assessed:
            return
        classroom_ceiling_comparisons.labels(
            state.ceiling_prediction, observed, result, state.ceiling_source,
        ).inc()
        AdaptiveSession.event(state, "ceiling_accuracy", predicted=state.ceiling_prediction,
                              observed=observed, result=result, source=state.ceiling_source)
        state.ceiling_assessed = True

    @staticmethod
    def demonstrated_rung(state) -> str:
        if state.independent_application:
            return "independent"
        if state.faded_targets:
            return "faded"
        if state.guided_targets:
            return "guided"
        return "none"

    def confirm_ceiling(self, state, pending) -> None:
        predicted = state.ceiling_prediction
        if predicted is None or state.ceiling_assessed or pending.task.kind == "explain":
            return
        if pending.phase != predicted or pending.extra_help_used:
            return
        if predicted in ("independent", "faded") and pending.assisted:
            # Faded tasks are scaffolded in the state, but an answer without
            # extra help still demonstrates that rung. Independent is unaided.
            if predicted == "independent":
                return
        if predicted == "independent" and (
            pending.task.kind != "apply" or not (
                state.challenge_requested or all(i in state.faded_targets for i in range(len(state.unit.targets)))
            )
        ):
            return
        self.compare_ceiling(state, pending.phase, "confirmed")

    @staticmethod
    def withdraw_ceiling(state):
        """Drop what the opening tap claimed, once the learner's work disagrees.

        Both the ceiling and the misconception behind it come from one tap,
        taken before the unit had taught anything. The moment the learner's own
        work says otherwise the tap stops having a say, and the unit is paced by
        what they do.

        The misconception goes with the ceiling rather than outliving it.
        `AdaptiveTeacher.turn` sends it on every later payload and the prompt
        teaches against it by name, so leaving it behind would aim the next
        reteaching at the error the learner made before the lesson started
        instead of the one they just made — which is the teacher not listening.
        """
        AdaptiveSession.compare_ceiling(state, AdaptiveSession.demonstrated_rung(state), "contradicted")
        state.diagnostic_ceiling = None
        state.diagnostic_misconception = ""

    #: How recent a demonstration has to be to stand in for the probe. Past
    #: this the record describes a learner who may have moved on: skills decay,
    #: and one cheap question beats assuming they still have it.
    RECORD_ANSWERS_WITHIN = timedelta(days=14)

    #: And how strong. 0.7 is the line the rest of the product already draws
    #: between "has met this" and "has this".
    RECORD_ANSWERS_ABOVE = 0.7

    @staticmethod
    def _same_skill(key: str | None) -> str | None:
        """Name a skill the way the writer of the evidence named it.

        Evidence is persisted through `_canonical_concept_id`, which leaves a
        `Concept` row's UUID alone and slugifies anything else. Comparing a
        raw title against that store never matches — "Compare Fractions" is
        not `compare_fractions` — so the probe shortcut silently never fired
        for any session without a resolved skill identity. Both sides go
        through the same canonicalisation here.
        """
        from lyo_app.events.mastery_projection import is_concept_graph_id

        key = (key or "").strip()
        if not key:
            return None
        return key if is_concept_graph_id(key) else slugify_skill(key)

    def record_answers_the_probe(self, context, state):
        """Recent, consistent evidence on this unit's own skill, if there is any.

        The probe exists because nothing ever asked where the learner was. Once
        they have a record on this skill, something already did — and asking
        again spends their time to learn what the server was told last week.
        Worse, it reads as a teacher who was not paying attention.

        Deliberately narrow. It wants this unit's skill and not a neighbouring
        one, evidence strong enough to act on, a history that agrees with it,
        and a demonstration recent enough to still describe them. Anything
        short of that and the unit asks, because asking costs one tap.

        "Agrees with it" is a success rate, not a streak. `KnowledgeState`
        carries `consecutive_incorrect`, and an earlier version of this check
        read it — but nothing populates it on the canonical mastery path,
        where it is always zero, and on the legacy path it holds a *lifetime*
        incorrect count. So it was dead in one direction and permanently
        disqualifying in the other. Attempts and successes are written on both
        paths, so they are what this asks about.
        """
        concept = self.record_concept(context, state)
        wanted = self._same_skill(concept)
        if not wanted:
            return None
        for known in context.knowledge_states:
            if self._same_skill(known.concept_id) != wanted:
                continue
            if known.total_attempts < 1 or known.mastery_level < self.RECORD_ANSWERS_ABOVE:
                return None
            if known.successes < self.RECORD_ANSWERS_ABOVE * known.total_attempts:
                return None
            if known.last_attempt is None:
                return None
            seen = known.last_attempt
            if seen.tzinfo is not None:
                seen = seen.astimezone(timezone.utc).replace(tzinfo=None)
            if datetime.utcnow() - seen > self.RECORD_ANSWERS_WITHIN:
                return None
            return known
        return None

    def open_unit(self, context, state) -> None:
        """Begin a unit: ask the probe, unless the record already answers it.

        Where the record answers it, the unit starts exactly where a correct tap
        would start it — supported practice, with `independent` as the ceiling.
        Not higher: a record says the learner could do this once, and one
        supported question confirms that cheaply, where starting above them on
        a stale record drops them into work they cannot do.
        """
        known = self.record_answers_the_probe(context, state)
        if known is None:
            return
        state.diagnosed = True
        state.diagnostic_ceiling = "independent"
        state.ceiling_prediction = "independent"
        state.ceiling_source = "record"
        classroom_diagnostics.labels("record").inc()
        state.phase = state.next_move = "guided"
        state.last_feedback = self.copy(
            context,
            "You've done this recently, so let's pick up where you left off.",
            "Ya trabajaste esto hace poco, así que retomemos donde lo dejaste.")
        self.event(state, "diagnostic", phase="diagnose", verdict="answered_by_record",
                   target=state.target_index, unaided=True, response_format="record",
                   mastery=round(float(known.mastery_level), 2),
                   attempts=int(known.total_attempts))

    def schedule_review(self, context, state, passed: bool) -> None:
        """Put this unit's skill into the learner's review schedule, once.

        Spaced retrieval is the difference between a lesson that went well and
        a skill the learner still has next month, and the classroom never
        reached the scheduler. Its only writers were Chat's answer check and
        the review endpoints — which can update a schedule but not create one —
        so a learner taught here had nothing ever come due, `review_due_items`
        stayed empty however much they learned, and the summary's "try a fresh
        example in a later session" was an invitation with no mechanism behind
        it.

        One write per unit, at the moment the unit's fate is decided. SM-2
        counts every write as a separate sitting — `next_schedule` advances
        `repetitions` on each call — so writing once per checkpoint would
        inflate the interval as though four days had passed inside one lesson.

        The grade is the pass/fail mapping the chat path already uses, not a
        finer judgement this engine can support: a unit closed by unaided
        independent application passes, and one filed for more practice fails,
        which resets the ladder so the skill comes back tomorrow. `hints_used`
        on the evidence already records how much help it took.
        """
        concept = self.record_concept(context, state)
        if not concept:
            return
        review = dict(
            user_id=context.user_id, concept_id=concept, passed=passed,
            decided_at=datetime.now(timezone.utc).isoformat(), unit_index=state.unit_index,
        )
        state.review_history = [*state.review_history, review]
        # The scheduler's interface takes only these four fields.
        state.review_outbox = [*state.review_outbox, {k: review[k] for k in (
            "user_id", "concept_id", "passed", "decided_at"
        )}]

    def record_practice(self, context, state, pending, result, data):
        evidence_type = None if pending.task.response_format == "choice" else (
            "transfer" if pending.phase == "transfer" and not pending.assisted
            and not pending.extra_help_used else
            "retrieval" if pending.phase == "interleave" and state.review_is_due
            and not pending.assisted and not pending.extra_help_used else
            "application" if pending.task.kind == "apply" else "explanation"
        )
        state.outbox.append(dict(
            event_id=pending.id, user_id=context.user_id,
            concept_id=self.record_concept(context, state),
            correct=result.verdict == "correct", evidence_type=evidence_type,
            hints_used=pending.hints_used, hint_level=pending.hint_level,
            misconception=result.misconception if result.verdict == "incorrect" else None,
            response_time_ms=data.get("response_time_ms"),
        ))

    def start_interleave(self, context, state) -> bool:
        """One earlier skill, inside a later unit, after normal practice starts."""
        if state.phase == "transfer" or state.active_review_index is not None:
            return False
        from lyo_app.events.mastery_projection import is_concept_graph_id
        key = lambda item: item if is_concept_graph_id(item) else slugify_skill(item)
        due = {key(item) for item in context.scheduled_due_items}
        candidates = [item for item in state.review_history
                      if item["unit_index"] < state.unit_index
                      and item["unit_index"] not in state.interleaved_units]
        if not candidates:
            return False
        candidates.sort(key=lambda item: (
            key(item["concept_id"]) not in due, item["unit_index"]
        ))
        item = candidates[0]
        state.active_review_index = item["unit_index"]
        state.review_return_phase = state.phase
        # A due schedule only supports a retention claim after a real time gap.
        # The due item must also name this exact skill. Old topic-scoped
        # schedules cannot prove retention of a newly scoped unit skill.
        # Same-sitting review after an independent success is application.
        age = datetime.now(timezone.utc) - datetime.fromisoformat(item["decided_at"])
        current_id = self.record_concept(context, state)
        state.review_is_due = (current_id is not None and
                               key(item["concept_id"]) == key(current_id) and
                               key(item["concept_id"]) in due and age >= timedelta(hours=20))
        state.phase = "interleave"
        return True

    @staticmethod
    def end_interleave(state) -> str:
        if state.active_review_index is not None:
            state.interleaved_units.append(state.active_review_index)
        state.active_review_index = None
        state.review_is_due = False
        state.phase = state.review_return_phase or "guided"
        state.review_return_phase = None
        state.pending = None
        return state.phase

    def finish_transfer(self, context, state) -> None:
        state.pending = None
        self.schedule_review(context, state, passed=state.independent_application)
        self.finish_unit(state)

    @staticmethod
    def after_success(state, pending):
        # An explanation is not a rung on the scaffolding ladder: it is asked
        # beside it, once, and moves the learner neither up nor down. Recording
        # that it happened is all it changes, and its evidence files as
        # `explanation` because that is what it is.
        if pending.task.kind == "explain":
            state.explained = True
            return False
        target = pending.task.target_index
        if pending.phase == "guided":
            state.guided_targets = sorted(set([*state.guided_targets, target]))
            state.phase = "faded"
        elif pending.phase == "faded":
            if not pending.extra_help_used:
                state.faded_targets = sorted(set([*state.faded_targets, target]))
            missing = [i for i in range(len(state.unit.targets)) if i not in state.faded_targets]
            if missing:
                state.target_index = missing[0]
                # A learner the probe placed at the top of the unit, who has
                # since shown it on real work, does not go back to supported
                # practice for each remaining component skill. This is the only
                # place the opening tap buys back the time it cost, and it buys
                # it only after unaided faded practice has confirmed the tap.
                confirmed = state.diagnostic_ceiling == "independent" and not pending.extra_help_used
                state.phase = ("faded" if missing[0] in state.guided_targets or confirmed
                               else "guided")
            else:
                state.phase = "independent"
        elif pending.phase == "independent":
            ready = all(i in state.faded_targets for i in range(len(state.unit.targets)))
            if ((ready or state.challenge_requested) and pending.task.kind == "apply"
                    and not pending.assisted and pending.task.response_format != "choice"):
                state.independent_application = True
                state.completed = sorted(set([*state.completed, state.unit_index]))
                state.skipped = [i for i in state.skipped if i != state.unit_index]
                state.phase = "transfer"
                return False
            state.phase = "faded" if target in state.guided_targets else "guided"
        return False

    @staticmethod
    def reset_unit(state):
        state.diagnostic_ceiling = None
        state.ceiling_prediction = None
        state.ceiling_source = "tap"
        state.ceiling_assessed = False
        state.unit_outcome_recorded = False
        state.diagnostic_misconception = ""
        state.explained = False
        state.closing_win_asked = False
        state.unit_done = False
        state.successes = 0
        state.independent_application = False
        state.task_kinds = []
        state.pending = state.presentation = state.paused_presentation = None
        state.last_feedback = ""
        state.generation_input = ""
        state.phase = state.next_move = "diagnose"
        state.guided_targets = []
        state.faded_targets = []
        state.target_index = state.model_steps_seen = state.support_attempts = 0
        state.return_to_checkpoint = state.challenge_requested = False
        state.active_review_index = None
        state.review_return_phase = None
        state.review_is_due = False
        state.diagnosed = False
        state.step_id = str(uuid4())

    @staticmethod
    def finish_unit(state):
        if not state.unit_outcome_recorded:
            AdaptiveSession.compare_ceiling(
                state, AdaptiveSession.demonstrated_rung(state), "unresolved"
            )
            classroom_unit_outcomes.labels(
                "completed" if state.independent_application else "needs_practice"
            ).inc()
            state.unit_outcome_recorded = True
        state.unit_done = bool(state.remaining_units)
        state.path_done = not state.remaining_units
        state.step_id = str(uuid4())
        state.presentation = state.paused_presentation = None
        state.return_to_checkpoint = False

    @staticmethod
    def current_continue(state, trigger):
        # Older installed native clients use static Continue identifiers.
        # Updated clients send the actual CTA ID, making double taps idempotent.
        return trigger.component_id in (state.step_id, None, "continue", "web_continue", "android_continue")

    @staticmethod
    def copy(context, en: str, es: str) -> str:
        return es if context.language_code.lower().startswith("es") else en

    @staticmethod
    def handled(state, component_id):
        state.handled = [*state.handled, component_id][-160:]

    @staticmethod
    def event(state, kind, **fields):
        state.practice_events = [*state.practice_events, dict(
            kind=kind, unit=state.unit_index, at=datetime.now(timezone.utc).isoformat(), **fields,
        )][-200:]

    @staticmethod
    def remember_beat(state, beat):
        content = beat.speech + "\n" + beat.board_content
        if beat.visual:
            content += "\n" + beat.visual.description
        state.taught_steps = [*state.taught_steps, content][-16:]

    @staticmethod
    def current_beat(state):
        return state.presentation if state.beat_index < 0 else state.presentation.demonstration[state.beat_index]

    @staticmethod
    def save(progress, state, scene):
        if state.record_scope == "unit":
            # Scene start travels on every reconnect. List the skills already
            # encountered so the record panel can place their evidence in this
            # class even when a new device has no earlier board history.
            indices = sorted(set([*state.completed, *state.skipped, state.unit_index]))
            scene.metadata.target_concepts = [
                state.skill_ids[i] if state.identity_required and i < len(state.skill_ids)
                else state.plan.units[i].title for i in indices
                if not state.identity_required or i < len(state.skill_ids)
            ]
        state.scene = scene.model_dump(mode="json")
        progress["guided_state"] = state.model_dump(mode="json")
        return scene

    def stage(self, context, state):
        return self.copy(context, {
            "diagnose": "Where you're starting",
            "orient": "Our goal", "model": "Watch me", "guided": "Let's do it together",
            "faded": "Finish this step", "independent": "Try it yourself",
            "transfer": "Use it somewhere new", "interleave": "Revisit an earlier idea",
        }[state.phase], {
            "diagnose": "Dónde empiezas",
            "orient": "Nuestra meta", "model": "Mira cómo", "guided": "Hagámoslo juntos",
            "faded": "Completa este paso", "independent": "Inténtalo tú",
            "transfer": "Úsalo en otro contexto", "interleave": "Repasa una idea anterior",
        }[state.phase])

    def surface(self, context, state, speech, title, content, visual=None, activity_id=None):
        title = self.stage(context, state) + " · " + title
        if len(title) > 100:
            title = title[:99].rstrip() + "…"
        example_content = content + "\n\n" + visual.description if visual else content
        separate_description = len(example_content) > 1500
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units), label=self.stage(context, state), priority=0),
            TeacherMessage(text=speech, language_code=context.language_code,
                           concept_tags=[state.plan.units[state.active_review_index].title
                                         if state.active_review_index is not None else state.unit.title],
                           emotion="encouraging", priority=1, source_attributions=context.source_attributions[:5]),
            ExampleBlock(title=title,
                         content=content if separate_description else example_content,
                         language_code=context.language_code, priority=2),
        ]
        if separate_description:
            # Preserve both full explanations instead of truncating teaching
            # to satisfy a limit on a single legacy component.
            components.append(ExampleBlock(title=visual.title, content=visual.description,
                                           language_code=context.language_code, priority=2))
        if visual:
            components.append(LessonBlock(component_id="visual:" + activity_id, block_type="teaching_visual",
                                          block=visual.model_dump(mode="json"), priority=3))
        return components

    def presentation_scene(self, context, state):
        beat = self.current_beat(state)
        speech = " ".join(p for p in (state.last_feedback if state.beat_index < 0 else "", beat.speech) if p)
        components = self.surface(context, state, speech, beat.board_title, beat.board_content,
                                  beat.visual, state.step_id)
        if state.next_move in ("reteach", "prerequisite") and state.beat_index < 0 and state.last_feedback:
            response = next((e.get("response", "") for e in reversed(state.practice_events)
                             if e.get("kind") == "response" and e.get("unit") == state.unit_index), "")
            answer = response if len(response) <= 600 else response[:599].rstrip() + "…"
            explanation = (self.copy(context, "Your answer: ", "Tu respuesta: ") + answer + "\n\n" if answer else "") + state.last_feedback
            components.insert(2, ExampleBlock(
                title=self.copy(context, "Let's work through your answer", "Revisemos tu respuesta"),
                content=explanation, language_code=context.language_code, priority=2,
            ))
        more = state.beat_index + 1 < len(state.presentation.demonstration)
        label = self.copy(context,
            "Show me the first step" if state.phase == "orient" else "Next step" if more else
            "Back to our example" if state.paused_presentation else "Back to our question" if state.return_to_checkpoint else
            "Continue learning" if state.support_attempts >= 2 and state.next_move in ("reteach", "prerequisite") else "Let's try together",
            "Ver el primer paso" if state.phase == "orient" else "Siguiente paso" if more else
            "Volver al ejemplo" if state.paused_presentation else "Volver a la pregunta" if state.return_to_checkpoint else
            "Seguir aprendiendo" if state.support_attempts >= 2 and state.next_move in ("reteach", "prerequisite") else "Practiquemos juntos")
        components.append(CTAButton(component_id=state.step_id, label=label, action_intent=ActionIntent.CONTINUE,
                                    language_code=context.language_code))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def checkpoint(self, context, state, follow_up=False):
        pending, task = state.pending, state.pending.task
        follow_up = follow_up or bool(pending.follow_up)
        speech = pending.feedback if follow_up else " ".join(p for p in (state.last_feedback, pending.speech) if p)
        components = self.surface(context, state, speech, pending.board_title, pending.board_content,
                                  pending.visual, pending.id)
        if follow_up and pending.answers:
            components.append(ExampleBlock(title=self.copy(context, "Your reasoning so far", "Tu razonamiento hasta ahora"),
                                            content="\n\n".join(pending.answers)[-1400:], language_code=context.language_code, priority=3))
        prompt = task.scenario + "\n\n" + (pending.follow_up if follow_up else task.question)
        # The opening probe is a choice, and an `apply` checkpoint may be one.
        # Neither may ship its key: the probe because the learner is still
        # deciding what they think, and `apply` because that is the checkpoint
        # whose answer counts.
        evidence_bearing = task.kind == "apply" or pending.phase == "diagnose"
        if task.response_format == "choice":
            components.append(QuizCard(
                component_id=pending.id, question=prompt,
                # Clients colour a tap instantly from the option's own
                # correctness rather than waiting for the server, which is
                # worth the round-trip it saves on ordinary practice. It
                # cannot be worth it for an `apply` checkpoint or the opening
                # diagnostic: the answer key would already be on the device
                # while the learner is deciding what they think.
                #
                # This was harmless while `choose` was the only kind that
                # could be answered by tapping — recognition never closed a
                # unit. Letting the format vary per checkpoint is what
                # brought a key to the question that counts.
                #
                # All three fields go together: Android reads a missing
                # `is_correct` as a neutral selection, but its feedback
                # lookup falls back to `feedback_incorrect`, so leaving the
                # text behind would tell a correct learner they were wrong.
                options=[QuizOption(id=o.id, label=o.label,
                                    is_correct=None if evidence_bearing else o.correct,
                                    feedback_correct=None if evidence_bearing or not o.correct else o.feedback,
                                    feedback_incorrect=None if evidence_bearing or o.correct else o.feedback)
                         for o in task.options],
                concept_id=self.record_concept(context, state), language_code=context.language_code, priority=4,
            ))
        else:
            components.append(InputField(
                component_id=pending.id, question=prompt + "\n\n" + task.response_hint, placeholder=task.response_hint,
                concept_id=self.record_concept(context, state),
                evidence_type="retrieval" if pending.phase == "interleave" and state.review_is_due
                else "transfer" if pending.phase == "transfer"
                else "application" if task.kind == "apply" else "explanation",
                min_words=1, max_words=200, expected_keywords=[], source_attributions=context.source_attributions[:5],
                language_code=context.language_code, priority=4,
            ))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def update_activity(self, context, progress, state, trigger):
        if not state.scene:
            return self.unavailable(context, state)
        activity_id = state.step_id if state.presentation else state.pending.id if state.pending else None
        visual = self.current_beat(state).visual if state.presentation else state.pending.visual if state.pending else None
        values = (trigger.action_data or {}).get("answer_data") or {}
        if trigger.component_id == "visual:" + str(activity_id) and visual and visual.update(values):
            # Preserve the scene and all component IDs; saving exploration must
            # neither replay the teacher nor turn the movement into an answer.
            for component in state.scene["components"]:
                if component.get("block_type") == "teaching_visual" and component["component_id"] == trigger.component_id:
                    component["block"] = visual.model_dump(mode="json")
            progress["guided_state"] = state.model_dump(mode="json")
        return Scene.model_validate(state.scene)

    def summary(self, context, state):
        title = self.copy(context, "What you practised", "Lo que practicaste")
        text = state.last_feedback or self.copy(context, "Let's bring the steps together.", "Vamos a reunir los pasos.")
        recap = state.unit.takeaway or state.unit.material
        if state.path_done:
            text += self.copy(context, " Try a fresh example in a later session to see what sticks.",
                              " Prueba un ejemplo nuevo en otra sesión para ver qué recuerdas.")
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units), label=title),
            TeacherMessage(text=text, emotion="encouraging", language_code=context.language_code),
            ExampleBlock(title=state.unit.title, content=recap[:1400], language_code=context.language_code),
            ExampleBlock(title=title, content="\n".join(
                f"• {u.title} — " + self.copy(context, "practised" if i in state.completed else "still to practise",
                    "practicada" if i in state.completed else "pendiente de práctica") for i, u in enumerate(state.plan.units)
            ), language_code=context.language_code),
        ]
        if not state.path_done or context.lesson_index + 1 < context.total_lessons:
            components.append(CTAButton(component_id=state.step_id, label=self.copy(context, "Continue learning", "Seguir aprendiendo"),
                                        action_intent=ActionIntent.CONTINUE, language_code=context.language_code))
        if state.path_done and context.lesson_index + 1 >= context.total_lessons:
            components.append(CTAButton(component_id=state.step_id, label=self.copy(context, "Try a fresh example", "Probar otro ejemplo"),
                                        action_intent=ActionIntent.REQUEST_REVIEW, language_code=context.language_code))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    #: How much of the last taught step to re-present while a turn is retried.
    _PAUSED_TEACHING_CHARS = 700

    def paused_notice(self, context) -> str:
        """The failure, in the learner's language, for the screen — never for the teacher.

        This sentence names a server problem and asks the learner to press a
        button. It is a product notice, so it belongs on the board beside the
        Retry control that acts on it, not in `TeacherMessage`, which is the
        teacher's voice and is narrated aloud.

        A teacher who apologises for the backend stops being a teacher. It was
        also the most repeated line in the product: every generation failure
        spoke it, so a learner on a bad connection heard their teacher say
        "I couldn't prepare the next step" over and over. The failure is real
        and must be visible — it is what the Retry button is for — but saying
        it in the teacher's voice charges the lesson for an outage.
        """
        return self.copy(
            context,
            "This lesson is paused because the next step didn't load. Nothing you've "
            "done is lost and this doesn't count as a wrong answer. Press Retry to carry on.",
            "Esta lección está en pausa porque el siguiente paso no se cargó. No se ha "
            "perdido nada de tu trabajo y esto no cuenta como error. Pulsa Reintentar para continuar.",
        )

    def paused_teaching(self, context, state) -> str:
        """What the teacher says instead: the lesson, again, from what we already hold.

        Never an apology and never about the server. The material the learner
        was working on is in session state, so the teacher can keep teaching
        from it while the screen carries the notice and the retry. Every branch
        reads values that are already present — this runs on the error path,
        and a recovery that raises leaves the dead screen it exists to prevent.
        """
        subject = ""
        if state:
            subject = (state.unit.title or "").strip()
        subject = subject or (context.lesson_title or context.topic or "").strip()
        material = ""
        if state:
            material = (state.taught_steps[-1] if state.taught_steps else state.unit.material) or ""
        material = (material or context.lesson_content or "").strip()[:self._PAUSED_TEACHING_CHARS]

        lead = self.copy(
            context,
            f"Let's stay with {subject} a moment longer." if subject else "Let's take the main idea again.",
            f"Quedémonos un momento más con {subject}." if subject else "Retomemos la idea principal.",
        )
        return (lead + "\n\n" + material).strip() if material else lead

    def unavailable(self, context, state):
        ungraded = bool(state and state.pending and state.pending.retry_response is not None)
        text = (self.copy(
            context,
            "Your answer couldn't be graded. It's saved and won't count as wrong. "
            "Continue with a fresh example.",
            "No pude evaluar tu respuesta. Está guardada y no contará como error. "
            "Continúa con un ejemplo nuevo.",
        ) if ungraded else self.paused_notice(context))
        components = [TeacherMessage(text=self.paused_teaching(context, state),
                                     emotion="encouraging", language_code=context.language_code)]
        # Keep the visible example, even after the final modelling beat has
        # advanced and no question was successfully installed. Recovery notices
        # are replaced, never accumulated across repeated failed attempts.
        examples = [ExampleBlock.model_validate(c) for c in (state.scene or {}).get("components", [])
                    if c.get("type") == "ExampleBlock" and not c.get("component_id", "").startswith("classroom-recovery/")] if state else []
        components.extend(examples[:3])
        if not examples:
            material = ((state.pending.board_content if state.pending else "")
                        or (state.taught_steps[-1] if state.taught_steps else "")
                        or state.unit.material) if state else context.lesson_content or ""
            for index in range(0, min(len(material), 4500), 1500):
                components.append(ExampleBlock(
                    title=self.copy(context, "Your example to revisit", "Tu ejemplo para repasar"),
                    content=material[index:index + 1500], language_code=context.language_code))
        if state and state.pending and state.pending.retry_response is not None:
            response = state.pending.retry_response
            for index in range(0, len(response), 1500):
                components.append(ExampleBlock(component_id=f"classroom-recovery/answer/{index}",
                    title=self.copy(context, "Your answer — not graded", "Tu respuesta — sin evaluar"),
                    content=response[index:index + 1500], language_code=context.language_code))
        elif state and state.last_feedback:
            components.append(ExampleBlock(component_id="classroom-recovery/feedback",
                title=self.copy(context, "About your answer", "Sobre tu respuesta"),
                content=state.last_feedback, language_code=context.language_code))
        # The complete recovery message belongs on the board as well as in
        # narration: a muted phone's two-line caption can otherwise hide it.
        components.append(ExampleBlock(component_id="classroom-recovery/notice",
            title=self.copy(context, "Your lesson is paused", "Tu lección está en pausa"),
            content=text, language_code=context.language_code))
        components.append(CTAButton(
            label=self.copy(context, "Continue with a new example", "Continuar con otro ejemplo")
            if ungraded else self.copy(context, "Retry this step", "Reintentar este paso"),
            action_intent=ActionIntent.SKIP_QUESTION if ungraded else ActionIntent.RETRY,
            language_code=context.language_code))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def current_or_retry(self, context, state):
        return Scene.model_validate(state.scene) if state.scene else self.unavailable(context, state)
