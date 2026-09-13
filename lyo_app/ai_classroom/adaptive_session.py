"""One server-owned teaching sequence for audio, silent, web and native clients."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, Evaluation, GuidedState, LearningTurn, PendingTask, TeachingUnavailable,
    normalize_text, requests_help,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, CTAButton, ExampleBlock, InputField, LessonBlock, ProgressBar, QuizCard,
    QuizOption, Scene, SceneType, TeacherMessage,
)


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
                phase="independent" if challenge else "orient",
                next_move="independent" if challenge else "orient",
            )
            progress["course_complete"] = False
            progress["guided_state"] = state.model_dump()

        if data.get("welcome") and state.scene:
            return Scene.model_validate(state.scene)
        if intent == ActionIntent.UPDATE_ACTIVITY:
            return self.update_activity(context, progress, state, trigger)
        if trigger.component_id in state.handled and state.scene:
            return Scene.model_validate(state.scene)
        state.mode = context.classroom_mode.value
        learner_input = str(data.get("message") or data.get("text") or data.get("question") or "")[:2000]

        if (state.unit_done or state.path_done) and intent in (
            ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE,
            ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE,
        ):
            self.reset_unit(state)
            state.path_done = False
        if state.path_done and intent == ActionIntent.REQUEST_REVIEW:
            itinerary = sorted(set(state.skipped)) or list(range(len(state.plan.units)))
            state.unit_index, state.remaining_units = itinerary[0], itinerary[1:]
            self.reset_unit(state)
            state.path_done = False
            state.challenge_requested = True
            state.phase = state.next_move = "independent"
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
            state.phase = state.next_move = "guided"
        elif state.presentation and intent in (
            ActionIntent.SUBMIT_ANSWER, ActionIntent.SUBMIT_TRANSFER, ActionIntent.RETRY,
        ):
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
                       response_format=pending.task.response_format)
            if result.verdict == "partial" and pending.attempts < 3:
                pending.assisted = pending.extra_help_used = True
                pending.hints_used += 1
                pending.hint_level = pending.hint_level or "principle"
                pending.follow_up = result.follow_up
                pending.id = str(uuid4())
                return self.save(progress, state, self.checkpoint(context, state, follow_up=True))
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
            state.return_to_checkpoint = pending is not None and pending.id not in state.handled
            if pending:
                pending.assisted = pending.extra_help_used = True
                pending.hints_used += 1
                pending.hint_level = "full_example" if intent == ActionIntent.REQUEST_EXAMPLE else "worked_step"
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
        elif state.presentation:
            return self.save(progress, state, self.presentation_scene(context, state))
        elif pending and pending.id not in state.handled:
            return self.save(progress, state, self.checkpoint(context, state))

        state.next_move = move
        try:
            turn = await self.teacher.turn(context, state, move, learner_input)
        except TeachingUnavailable:
            return self.save(progress, state, self.unavailable(context, state))
        self.remember_beat(state, turn)
        if turn.task is None:
            if not state.return_to_checkpoint:
                state.pending = None
            state.presentation = turn
            state.beat_index = -1
            state.step_id = str(uuid4())
            state.phase = "orient" if move == "orient" else "model"
            return self.save(progress, state, self.presentation_scene(context, state))

        state.presentation = None
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
        state.phase = state.next_move = "orient"
        state.guided_targets = []
        state.faded_targets = []
        state.target_index = state.model_steps_seen = state.support_attempts = 0
        state.return_to_checkpoint = state.challenge_requested = False
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
            "orient": "Our goal", "model": "Watch me", "guided": "Let's do it together",
            "faded": "Finish this step", "independent": "Try it yourself",
        }[state.phase], {
            "orient": "Nuestra meta", "model": "Mira cómo", "guided": "Hagámoslo juntos",
            "faded": "Completa este paso", "independent": "Inténtalo tú",
        }[state.phase])

    def surface(self, context, state, speech, title, content, visual=None, activity_id=None):
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units), label=self.stage(context, state), priority=0),
            TeacherMessage(text=speech, language_code=context.language_code, concept_tags=[state.unit.title],
                           emotion="encouraging", priority=1, source_attributions=context.source_attributions[:5]),
            ExampleBlock(title=self.stage(context, state) + " · " + title,
                         content=(content + "\n\n" + visual.description) if visual else content,
                         language_code=context.language_code, priority=2),
        ]
        if visual:
            components.append(LessonBlock(component_id="visual:" + activity_id, block_type="teaching_visual",
                                          block=visual.model_dump(mode="json"), priority=3))
        return components

    def presentation_scene(self, context, state):
        beat = self.current_beat(state)
        speech = " ".join(p for p in (state.last_feedback if state.beat_index < 0 else "", beat.speech) if p)
        components = self.surface(context, state, speech, beat.board_title, beat.board_content,
                                  beat.visual, state.step_id)
        more = state.beat_index + 1 < len(state.presentation.demonstration)
        label = self.copy(context,
            "Show me the first step" if state.phase == "orient" else "Next step" if more else
            "Back to our example" if state.paused_presentation else "Back to our question" if state.return_to_checkpoint else "Let's try together",
            "Ver el primer paso" if state.phase == "orient" else "Siguiente paso" if more else
            "Volver al ejemplo" if state.paused_presentation else "Volver a la pregunta" if state.return_to_checkpoint else "Practiquemos juntos")
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
        if task.response_format == "choice":
            components.append(QuizCard(
                component_id=pending.id, question=prompt,
                options=[QuizOption(id=o.id, label=o.label, is_correct=o.correct,
                                    feedback_correct=o.feedback if o.correct else None,
                                    feedback_incorrect=o.feedback if not o.correct else None) for o in task.options],
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

    def unavailable(self, context, state):
        text = self.copy(context, "I couldn't prepare the next step reliably. Nothing is marked wrong. Please retry, or pause here.",
                        "No pude preparar el siguiente paso con confianza. No cuenta como error. Reintenta o pausa aquí.")
        components = [TeacherMessage(text=text, language_code=context.language_code)]
        if state and state.pending and state.pending.retry_response is not None:
            components.append(ExampleBlock(title=self.copy(context, "Your answer — not graded", "Tu respuesta — sin evaluar"),
                                            content=state.pending.retry_response[:1400], language_code=context.language_code))
        else:
            material = (state.pending.board_content if state and state.pending else context.lesson_content) or ""
            if material.strip():
                components.append(ExampleBlock(title=self.copy(context, "Your example to revisit", "Tu ejemplo para repasar"),
                                                content=material[:1400], language_code=context.language_code))
        components.append(CTAButton(label=self.copy(context, "Retry this step", "Reintentar este paso"),
                                    action_intent=ActionIntent.RETRY, language_code=context.language_code))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def current_or_retry(self, context, state):
        return Scene.model_validate(state.scene) if state.scene else self.unavailable(context, state)
