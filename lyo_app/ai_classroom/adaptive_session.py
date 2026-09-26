"""One server-owned teaching sequence for audio, silent, web and native clients."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, Evaluation, GuidedState, LearningTurn, PendingTask, TeachingUnavailable,
    normalize_text, requests_help, validation_summary,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, CTAButton, ExampleBlock, InputField, LessonBlock, ProgressBar, QuizCard,
    QuizOption, Scene, SceneType, TeacherMessage,
)

logger = logging.getLogger(__name__)


class AdaptiveSession:
    def __init__(self, teacher: AdaptiveTeacher):
        self.teacher = teacher

    async def run(self, context, progress: dict[str, Any], trigger) -> Scene:
        data = trigger.action_data or {}
        intent = data.get("action_intent")
        raw = progress.get("guided_state")
        state = GuidedState.model_validate(raw) if raw else None
        if state and state.owner != context.user_id:
            raise ValueError("Guided session owner mismatch")
        if state is None:
            if intent == ActionIntent.UPDATE_ACTIVITY:
                return self.unavailable(context, None)
            try:
                plan = await self.teacher.plan(context)
            except TeachingUnavailable:
                return self.unavailable(context, None)
            challenge = context.classroom_mode.value in ("challenge", "review")
            state = GuidedState(
                owner=context.user_id, course_id=context.course_id,
                lesson_id=context.lesson_id, lesson_index=context.lesson_index,
                plan=plan, mode=context.classroom_mode.value,
                remaining_units=list(range(1, len(plan.units))),
                challenge_requested=challenge,
                phase="independent" if challenge else "diagnose",
                next_move="independent" if challenge else "diagnose",
            )
            progress["course_complete"] = False
            progress["guided_state"] = state.model_dump()

        if data.get("welcome") and state.scene:
            return Scene.model_validate(state.scene)
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

        # Demonstrations are paced by explicit, identifiable Continue events.
        # Asking a question may interrupt them without throwing the example away.
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
                if state.unit_index not in state.skipped and state.unit_index not in state.completed:
                    state.skipped.append(state.unit_index)
                self.event(state, "practise_later", phase=state.phase, reason="continued_after_support")
                state.last_feedback = self.copy(context,
                    "We've worked through the tricky step together. Let's keep learning and revisit this skill for more practice.",
                    "Revisamos juntos el paso difícil. Sigamos aprendiendo y volvamos a esta habilidad para practicarla más.")
                self.finish_unit(state)
                return self.save(progress, state, self.summary(context, state))
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
            intent in (ActionIntent.CONTINUE, ActionIntent.RETRY) and pending is not None
            and pending.retry_response is not None and pending.task.response_format != "choice"
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
            if pending.phase == "diagnose":
                move = self.after_diagnostic(context, state, pending, result, response,
                                             response_time_ms=data.get("response_time_ms"))
            elif result.verdict == "partial" and pending.attempts < 3:
                pending.assisted = pending.extra_help_used = True
                pending.hints_used += 1
                pending.hint_level = pending.hint_level or "principle"
                pending.follow_up = result.follow_up
                pending.id = str(uuid4())
                return self.save(progress, state, self.checkpoint(context, state, follow_up=True))
            else:
                if result.verdict in ("correct", "incorrect"):
                    state.outbox.append(dict(
                        event_id=pending.id, user_id=context.user_id,
                        concept_id=context.lesson_title or context.topic,
                        correct=result.verdict == "correct",
                        evidence_type=None if choice else "application" if pending.task.kind == "apply" else "explanation",
                        hints_used=pending.hints_used, hint_level=pending.hint_level,
                        misconception=result.misconception if result.verdict == "incorrect" else None,
                        response_time_ms=data.get("response_time_ms"),
                    ))
                if result.verdict == "correct":
                    state.successes += 1
                    state.support_attempts = 0
                    if self.after_success(state, pending):
                        state.pending = None
                        return self.save(progress, state, self.summary(context, state))
                    move = state.phase
                elif result.verdict == "clarify":
                    # Ambiguous wording and requests for help are not failures.
                    move = "help" if requests_help(response) else "clarify"
                    state.return_to_checkpoint = requests_help(response)
                    pending.assisted = pending.extra_help_used = True
                    pending.hints_used += 1
                    if state.return_to_checkpoint:
                        pending.id = str(uuid4())
                else:
                    state.support_attempts += 1
                    state.target_index = pending.task.target_index
                    state.faded_targets = [i for i in state.faded_targets if i != state.target_index]
                    move = "prerequisite" if state.support_attempts >= 2 else "reteach"
                    state.return_to_checkpoint = False
            learner_input = response

        elif intent == ActionIntent.SKIP_QUESTION:
            if not pending or trigger.component_id != pending.id:
                return self.current_or_retry(context, state)
            self.handled(state, pending.id)
            if pending.phase == "diagnose":
                # Passing on "can you already do this?" is itself an answer: no.
                # It must not mark the skill for later review the way skipping
                # practice does — the learner has asked to be taught it now.
                state.diagnosed = True
                state.return_to_checkpoint = False
                self.event(state, "diagnostic", phase="diagnose", verdict="declined",
                           target=pending.task.target_index)
                state.last_feedback = self.copy(
                    context, "No problem — let's build it from the start.",
                    "Sin problema: vamos a construirlo desde el principio.")
                state.phase = move = "orient"
            else:
                if state.unit_index not in state.skipped and state.unit_index not in state.completed:
                    state.skipped.append(state.unit_index)
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
            return self.save(progress, state, self.presentation_scene(context, state))

        state.presentation = None
        if move == "diagnose":
            # A probe is unsupported by definition — nothing has been taught
            # for it to lean on. Marking it assisted, as practice is, would
            # damp the confidence of the strongest demonstration this engine
            # can collect: the learner doing it before being shown how.
            phase, supported = "diagnose", False
        else:
            phase = state.phase if state.phase in ("guided", "faded", "independent") else "guided"
            supported = phase != "independent"
        state.pending = PendingTask(
            task=turn.task, speech=turn.speech, board_title=turn.board_title,
            board_content=turn.board_content, visual=turn.visual, phase=phase,
            assisted=supported, hints_used=1 if supported else 0,
            hint_level="worked_step" if supported else None, taught_steps=state.taught_steps.copy(),
        )
        state.task_kinds = [*state.task_kinds, turn.task.kind][-8:]
        state.recent_questions = [*state.recent_questions, normalize_text(turn.task.scenario + " " + turn.task.question)][-12:]
        state.next_move = phase
        return self.save(progress, state, self.checkpoint(context, state))

    def after_diagnostic(self, context, state, pending, result, response, response_time_ms=None) -> str:
        """Decide where this unit actually starts, from what the learner just showed.

        A diagnostic is the one checkpoint a learner cannot fail. It is asked
        before anything is taught, so a wrong answer says only that the unit
        has work to do — which is what the unit is for. Nothing here increments
        `support_attempts`, marks the unit for review, or reteaches an answer
        the learner was never given: those all read a wrong answer as a
        setback, and this one is the starting line.

        The three routes are the whole point of asking:

        * **Already has it** — skip the worked demonstration entirely and go
          straight to fading support. Sitting a learner through "watch me" on
          a skill they just performed is the single fastest way to lose them.
        * **Has part of it** — begin at guided practice, building on the part
          they showed rather than starting from zero.
        * **Does not have it yet** — teach it properly, now with the learner's
          own words and the named misconception in hand, so the explanation
          can address what they actually said.

        Evidence is written only for a correct, unaided probe, and it is the
        strongest thing this engine can record: performance before
        instruction. It is filed as `explanation`, never `transfer`, because
        transfer is defined relative to something taught and nothing was.

        An incorrect probe writes **no** evidence rather than a zero. "Measured
        at zero on a skill never taught" is a claim about the learner that the
        probe does not support, and the learner record keeps "not started"
        and "attempted and got nothing" apart deliberately.
        """
        state.diagnosed = True
        state.support_attempts = 0
        state.return_to_checkpoint = False
        unaided = not pending.assisted and not pending.extra_help_used
        self.event(state, "diagnostic", phase="diagnose", target=pending.task.target_index,
                   verdict=result.verdict, unaided=unaided,
                   response_format=pending.task.response_format, response=response,
                   misconception=result.misconception)

        if result.verdict == "correct" and unaided:
            state.outbox.append(dict(
                event_id=pending.id, user_id=context.user_id,
                concept_id=context.lesson_title or context.topic,
                correct=True, evidence_type="explanation",
                hints_used=0, hint_level=None, misconception=None,
                response_time_ms=response_time_ms,
            ))
            state.last_feedback = (result.feedback + " " + self.copy(
                context,
                "You already have this, so we won't sit through the basics.",
                "Ya dominas esto, así que no repasaremos lo básico.",
            )).strip()
            state.phase = "faded"
            return "faded"

        if result.verdict == "partial":
            state.phase = "guided"
            return "guided"

        # Wrong, unclear, or a request for help: teach it, starting from what
        # they said. `orient` reaches the generator with the learner's answer
        # and this feedback already in its payload.
        state.phase = "orient"
        return "orient"

    @staticmethod
    def after_success(state, pending):
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
                state.phase = "faded" if missing[0] in state.guided_targets else "guided"
            else:
                state.phase = "independent"
        elif pending.phase == "independent":
            ready = all(i in state.faded_targets for i in range(len(state.unit.targets)))
            if (ready or state.challenge_requested) and not pending.assisted and pending.task.response_format != "choice":
                state.independent_application = True
                state.completed = sorted(set([*state.completed, state.unit_index]))
                state.skipped = [i for i in state.skipped if i != state.unit_index]
                AdaptiveSession.finish_unit(state)
                return True
            state.phase = "faded" if target in state.guided_targets else "guided"
        return False

    @staticmethod
    def reset_unit(state):
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
        state.diagnosed = False
        state.step_id = str(uuid4())

    @staticmethod
    def finish_unit(state):
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
        state.scene = scene.model_dump(mode="json")
        progress["guided_state"] = state.model_dump(mode="json")
        return scene

    def stage(self, context, state):
        return self.copy(context, {
            "diagnose": "Where you're starting",
            "orient": "Our goal", "model": "Watch me", "guided": "Let's do it together",
            "faded": "Finish this step", "independent": "Try it yourself",
        }[state.phase], {
            "diagnose": "Dónde empiezas",
            "orient": "Nuestra meta", "model": "Mira cómo", "guided": "Hagámoslo juntos",
            "faded": "Completa este paso", "independent": "Inténtalo tú",
        }[state.phase])

    def surface(self, context, state, speech, title, content, visual=None, activity_id=None):
        title = self.stage(context, state) + " · " + title
        if len(title) > 100:
            title = title[:99].rstrip() + "…"
        example_content = content + "\n\n" + visual.description if visual else content
        separate_description = len(example_content) > 1500
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units), label=self.stage(context, state), priority=0),
            TeacherMessage(text=speech, language_code=context.language_code, concept_tags=[state.unit.title],
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
        evidence_bearing = task.kind == "apply"
        if task.response_format == "choice":
            components.append(QuizCard(
                component_id=pending.id, question=prompt,
                # Clients colour a tap instantly from the option's own
                # correctness rather than waiting for the server, which is
                # worth the round-trip it saves on practice. It cannot be
                # worth it here: an `apply` checkpoint is the one whose
                # correct answer banks application evidence and closes a
                # unit, and shipping its key puts the answer in the page
                # for anyone who opens it. Sending a key the learner can
                # read, for the one question that decides what the product
                # believes they can do, buys a few hundred milliseconds and
                # costs the record its meaning.
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
                concept_id=context.lesson_title or context.topic, language_code=context.language_code, priority=4,
            ))
        else:
            components.append(InputField(
                component_id=pending.id, question=prompt + "\n\n" + task.response_hint, placeholder=task.response_hint,
                concept_id=context.lesson_title or context.topic,
                evidence_type="application" if task.kind == "apply" else "explanation",
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
        text = self.paused_notice(context)
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
        components.append(CTAButton(label=self.copy(context, "Retry this step", "Reintentar este paso"),
                                    action_intent=ActionIntent.RETRY, language_code=context.language_code))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def current_or_retry(self, context, state):
        return Scene.model_validate(state.scene) if state.scene else self.unavailable(context, state)
