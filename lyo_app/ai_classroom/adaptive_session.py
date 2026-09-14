"""The shared live teaching loop, expressed using existing web/iOS/Android UI.

No client decides the next learning step or grading outcome. This runner is
driven only by explicit learner events; it never advances on elapsed time.
"""

from typing import Any
from uuid import uuid4

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, Evaluation, GuidedState, PendingTask, TeachingUnavailable,
    normalize_text, requests_help,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, CTAButton, ExampleBlock, InputField, ProgressBar, QuizCard,
    QuizOption, Scene, SceneType, TeacherMessage,
)


class AdaptiveSession:
    def __init__(self, teacher: AdaptiveTeacher):
        self.teacher = teacher

    async def run(self, context, progress: dict[str, Any], trigger) -> Scene:
        data = trigger.action_data or {}
        intent = data.get("action_intent")
        raw_state = progress.get("guided_state")
        state = GuidedState.model_validate(raw_state) if raw_state else None
        if state and state.owner != context.user_id:
            raise ValueError("Guided session owner mismatch")
        if state is None:
            try:
                plan = await self.teacher.plan(context)
            except TeachingUnavailable:
                return self.unavailable(context, None)
            state = GuidedState(
                owner=context.user_id, course_id=context.course_id,
                lesson_id=context.lesson_id, lesson_index=context.lesson_index,
                plan=plan, mode=context.classroom_mode.value,
                remaining_units=list(range(1, len(plan.units))),
            )
            # A legacy topic path with total_lessons=0 was not a completed
            # curriculum. Preserve its evidence separately, but do not carry
            # its synthetic completion into the new plan.
            progress["course_complete"] = False
            progress["guided_state"] = state.model_dump()

        # Restore the exact question/board and partial answers; opening a
        # classroom must not create a new teaching event or grade an old one.
        if data.get("welcome") and state.scene:
            return Scene.model_validate(state.scene)

        state.mode = context.classroom_mode.value
        if trigger.component_id in state.handled and state.scene:
            return Scene.model_validate(state.scene)

        if (state.unit_done or state.path_done) and intent in (
            ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE,
            ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE,
        ):
            # Finishing a step never closes the door on a learner's question.
            self.reset_unit(state)
            state.path_done = False

        if state.path_done and intent == ActionIntent.REQUEST_REVIEW:
            itinerary = sorted(set(state.skipped)) or list(range(len(state.plan.units)))
            state.unit_index, state.remaining_units = itinerary[0], itinerary[1:]
            self.reset_unit(state)
            state.path_done = False
        elif state.path_done:
            return self.save(progress, state, self.summary(context, state))

        if state.unit_done:
            if intent not in (ActionIntent.CONTINUE, ActionIntent.RETRY):
                return self.save(progress, state, self.summary(context, state))
            if not state.remaining_units:
                state.path_done = True
                return self.save(progress, state, self.summary(context, state))
            state.unit_index = state.remaining_units.pop(0)
            self.reset_unit(state)

        move = state.next_move
        learner_input = str(data.get("message") or data.get("text") or data.get("question") or "")[:2000]
        pending = state.pending
        answer = data.get("answer_data") or {}
        submitting = intent in (ActionIntent.SUBMIT_ANSWER, ActionIntent.SUBMIT_TRANSFER)
        retry_evaluation = (
            intent in (ActionIntent.CONTINUE, ActionIntent.RETRY)
            and pending is not None and pending.retry_response is not None
            and pending.task.kind != "choose"
        )

        if submitting or retry_evaluation:
            if not pending or (not retry_evaluation and trigger.component_id != pending.id):
                # Stale or duplicate deliveries cannot be marked wrong, steal
                # a different checkpoint, or consume another teaching step.
                return self.save(progress, state, self.current_or_retry(context, state))
            if retry_evaluation:
                response = pending.retry_response
            elif pending.task.kind == "choose":
                option = next((o for o in pending.task.options
                               if o.id == answer.get("selected_option_id")), None)
                if intent != ActionIntent.SUBMIT_ANSWER or option is None:
                    return self.save(progress, state, self.current_or_retry(context, state))
                response = option.label
            else:
                if intent != ActionIntent.SUBMIT_TRANSFER:
                    return self.save(progress, state, self.current_or_retry(context, state))
                response = str(answer.get("response") or learner_input).strip()[:2000]
            if not response:
                return self.save(progress, state, self.current_or_retry(context, state))

            if pending.task.kind == "choose":
                result = Evaluation(
                    verdict="correct" if option.correct else "incorrect", confidence=1,
                    misconception=option.misconception if not option.correct else None,
                    question_clear=True, feedback=option.feedback if len(option.feedback.split()) >= 3 else self.copy(
                        context, "Let's look at why that works." if option.correct else "Let's work through that decision together.",
                        "Veamos por qué funciona." if option.correct else "Revisemos juntos esa decisión."),
                )
            else:
                result = await self.teacher.evaluate(context, pending, response)

            pending.retry_response = None
            state.last_feedback = result.feedback
            if result.verdict == "unavailable":
                pending.retry_response = response
                return self.save(progress, state, self.unavailable(context, state))

            self.handled(state, pending.id)
            pending.answers.append(response)
            pending.answers = pending.answers[-5:]
            pending.attempts += 1
            pending.feedback = result.feedback
            if result.verdict == "partial" and pending.attempts < 3:
                pending.assisted = True
                pending.hints_used += 1
                pending.hint_level = pending.hint_level or "principle"
                pending.follow_up = result.follow_up
                pending.id = str(uuid4())
                return self.save(progress, state, self.checkpoint(context, state, follow_up=True))

            if result.verdict in ("correct", "incorrect"):
                # Recognition is not transfer. Guided/corrected applications
                # are useful evidence with support, not unaided mastery.
                kind = (
                    None if pending.task.kind == "choose" else
                    "application" if pending.task.kind == "apply" else "explanation"
                )
                state.outbox.append(dict(
                    event_id=pending.id,
                    user_id=context.user_id, concept_id=context.lesson_title or context.topic,
                    correct=result.verdict == "correct",
                    evidence_type=kind,
                    hints_used=pending.hints_used,
                    hint_level=pending.hint_level,
                    misconception=result.misconception if result.verdict == "incorrect" else None,
                    response_time_ms=data.get("response_time_ms"),
                ))

            if result.verdict == "correct":
                state.successes += 1
                state.independent_application |= pending.task.kind == "apply" and not pending.assisted
                if state.successes >= 2 and state.independent_application:
                    if state.unit_index not in state.completed:
                        state.completed.append(state.unit_index)
                    state.skipped = [i for i in state.skipped if i != state.unit_index]
                    self.finish_unit(state)
                    state.pending = None
                    return self.save(progress, state, self.summary(context, state))
                move = "independent"
            elif result.verdict == "clarify":
                move = "help" if requests_help(response) else "clarify"
            else:
                move = "reteach"
            learner_input = response
            # Retain the previous task and answers for authoring the next
            # response; it is already consumed, so it can never be graded twice.

        elif intent == ActionIntent.SKIP_QUESTION:
            if not pending or trigger.component_id != pending.id:
                return self.save(progress, state, self.current_or_retry(context, state))
            self.handled(state, pending.id)
            if state.unit_index not in state.skipped and state.unit_index not in state.completed:
                state.skipped.append(state.unit_index)
            self.finish_unit(state)
            state.pending = None
            state.last_feedback = self.copy(context,
                "Skipped without penalty. This skill remains available for practice.",
                "Omitida sin penalización. Esta habilidad queda pendiente de práctica.")
            return self.save(progress, state, self.summary(context, state))
        elif intent in (ActionIntent.REQUEST_HINT, ActionIntent.REQUEST_EXAMPLE):
            move = "help" if intent == ActionIntent.REQUEST_HINT else "reteach"
            if pending:
                self.handled(state, pending.id)
                pending.assisted = True
        elif intent in (ActionIntent.ASK_QUESTION, ActionIntent.USER_MESSAGE):
            move = "answer_question"
            if pending:
                self.handled(state, pending.id)
        elif intent == ActionIntent.SKIP_AHEAD:
            move = "independent"
            if pending:
                self.handled(state, pending.id)
        elif pending and pending.id not in state.handled:
            # An extra Continue can never bypass an unanswered checkpoint.
            return self.save(progress, state, self.checkpoint(context, state))

        state.next_move = move
        try:
            turn = await self.teacher.turn(context, state, move, learner_input)
        except TeachingUnavailable:
            return self.save(progress, state, self.unavailable(context, state))

        state.taught_steps = [*state.taught_steps[-5:], turn.speech + "\n" + turn.board_content]
        state.pending = PendingTask(
            task=turn.task, speech=turn.speech, board_title=turn.board_title,
            board_content=turn.board_content, assisted=move in ("help", "reteach", "clarify"),
            hints_used=(pending.hints_used + 1 if pending else 1) if move in ("help", "reteach", "clarify") else 0,
            hint_level="full_example" if move == "reteach" else "worked_step" if move in ("help", "clarify") else None,
            taught_steps=state.taught_steps.copy(),
        )
        state.task_kinds.append(turn.task.kind)
        state.task_kinds = state.task_kinds[-8:]
        state.recent_questions.append(normalize_text(turn.task.scenario + " " + turn.task.question))
        state.recent_questions = state.recent_questions[-12:]
        state.next_move = "teach"
        return self.save(progress, state, self.checkpoint(context, state))

    @staticmethod
    def reset_unit(state):
        state.unit_done = False
        state.successes = 0
        state.independent_application = False
        state.task_kinds = []
        state.pending = None
        state.last_feedback = ""
        state.next_move = "teach"

    @staticmethod
    def finish_unit(state):
        state.unit_done = bool(state.remaining_units)
        state.path_done = not state.remaining_units

    @staticmethod
    def copy(context, en: str, es: str) -> str:
        return es if context.language_code.lower().startswith("es") else en

    @staticmethod
    def handled(state: GuidedState, component_id: str):
        state.handled.append(component_id)
        state.handled = state.handled[-120:]

    @staticmethod
    def save(progress, state, scene):
        state.scene = scene.model_dump(mode="json")
        progress["guided_state"] = state.model_dump(mode="json")
        return scene

    def checkpoint(self, context, state: GuidedState, follow_up: bool = False) -> Scene:
        pending = state.pending
        follow_up = follow_up or bool(pending.follow_up)
        task = pending.task
        teacher_text = pending.feedback if follow_up else " ".join(
            part for part in (state.last_feedback, pending.speech) if part
        )
        # Feedback is a teaching beat, not a second lecture or a judgment label.
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units),
                        label=self.copy(context, "Skills practised", "Habilidades practicadas"), priority=0),
            TeacherMessage(text=teacher_text, language_code=context.language_code,
                           concept_tags=[state.unit.title], emotion="encouraging", priority=1,
                           source_attributions=context.source_attributions[:5]),
            ExampleBlock(title=state.unit.title if follow_up else pending.board_title,
                         content=pending.board_content, language_code=context.language_code, priority=2),
        ]
        # Keep partial answers visible without exposing the private rubric.
        if follow_up and pending.answers:
            components.append(ExampleBlock(
                title=self.copy(context, "Your reasoning so far", "Tu razonamiento hasta ahora"),
                content="\n\n".join(pending.answers)[-1400:],
                language_code=context.language_code, priority=3,
            ))
        prompt = task.scenario + "\n\n" + (
            pending.follow_up if follow_up else task.question
        )
        if task.kind == "choose":
            components.append(QuizCard(
                component_id=pending.id, question=prompt,
                options=[QuizOption(id=o.id, label=o.label, is_correct=o.correct,
                                    feedback_correct=o.feedback if o.correct else None,
                                    feedback_incorrect=o.feedback if not o.correct else None)
                         for o in task.options],
                concept_id=context.lesson_title or context.topic,
                language_code=context.language_code, priority=4,
            ))
        else:
            components.append(InputField(
                component_id=pending.id, question=prompt + "\n\n" + task.response_hint,
                placeholder=task.response_hint,
                concept_id=context.lesson_title or context.topic,
                evidence_type="application" if task.kind == "apply" else "explanation",
                # A number or concise correct sentence is a valid answer.
                min_words=1, max_words=200, expected_keywords=[],
                source_attributions=context.source_attributions[:5],
                language_code=context.language_code, priority=4,
            ))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def summary(self, context, state: GuidedState) -> Scene:
        all_units = state.path_done
        title = self.copy(context, "Practice summary", "Resumen de práctica")
        if all_units:
            text = self.copy(context,
                "This practice path is finished. Review later to check what you retain; this is not a mastery claim.",
                "Terminaste este recorrido de práctica. Repasa después para comprobar qué retienes; esto no confirma dominio.")
        else:
            text = state.last_feedback or self.copy(context,
                "You have practised this step. Continue when you are ready.",
                "Has practicado este paso. Continúa cuando estés listo.")
        content = "\n".join(
            f"• {unit.title} — " + self.copy(context,
                "practised" if index in state.completed else "still to practise",
                "practicada" if index in state.completed else "pendiente de práctica")
            for index, unit in enumerate(state.plan.units)
        )
        components = [
            ProgressBar(current=len(state.completed), total=len(state.plan.units), label=title),
            TeacherMessage(text=text, emotion="encouraging", language_code=context.language_code),
            ExampleBlock(title=title, content=content, language_code=context.language_code),
        ]
        if not all_units or context.lesson_index + 1 < context.total_lessons:
            label = self.copy(context, "Continue learning", "Seguir aprendiendo")
            components.append(CTAButton(label=label, action_intent=ActionIntent.CONTINUE,
                                        language_code=context.language_code))
        if all_units:
            components.append(CTAButton(
                label=self.copy(context, "Practise again", "Practicar de nuevo"),
                action_intent=ActionIntent.REQUEST_REVIEW, language_code=context.language_code,
            ))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def unavailable(self, context, state: GuidedState | None) -> Scene:
        text = self.copy(context,
            "I couldn't prepare the next step reliably. Nothing is marked wrong. Please retry, or pause here.",
            "No pude preparar el siguiente paso con confianza. No cuenta como error. Reintenta o pausa aquí.")
        components = [TeacherMessage(text=text, language_code=context.language_code)]
        if state and state.pending and state.pending.retry_response is not None:
            components.append(ExampleBlock(
                title=self.copy(context, "Your answer — not graded", "Tu respuesta — sin evaluar"),
                content=state.pending.retry_response[:1400], language_code=context.language_code,
            ))
        else:
            material = (state.pending.board_content if state and state.pending else context.lesson_content) or ""
            if material.strip():
                components.append(ExampleBlock(
                    title=self.copy(context, "Your example to revisit", "Tu ejemplo para repasar"),
                    content=material[:1400], language_code=context.language_code,
                ))
        components.append(CTAButton(
            label=self.copy(context, "Retry this step", "Reintentar este paso"),
            action_intent=ActionIntent.RETRY, language_code=context.language_code,
        ))
        return Scene(scene_type=SceneType.INSTRUCTION, components=components)

    def current_or_retry(self, context, state):
        if state.scene:
            return Scene.model_validate(state.scene)
        return self.unavailable(context, state)
