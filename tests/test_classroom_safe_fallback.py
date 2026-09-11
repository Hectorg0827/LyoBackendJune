"""The classroom must never dead-end when scene generation fails.

WHY THIS MATTERS MORE THAN IT LOOKS

iOS carried a 589-line on-device teaching engine whose own header explained
why it existed: the server-pushed classroom could stop streaming and the
screen "went dead". That engine has been removed — a client-side teaching
loop makes iOS a pedagogically different product from web and Android, which
is exactly what the cross-platform parity gate exists to prevent.

Removing the workaround means the weakness it covered has to be fixed on the
server, where every client benefits. Until it is, iOS is *less* protected
than before the removal.

What the learner used to get on this path was "Let's continue with one idea
at a time when you're ready." and a Continue button: no teaching, and no way
forward but to press the same button again.

These tests drive the real handler and assert on the scene a learner would
actually receive.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from lyo_app.ai_classroom.scene_lifecycle_engine import (
    _SESSION_PROGRESS,
    SceneLifecycleEngine,
    Trigger,
    TriggerType,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent, ComponentType

SESSION = "fallback-session"

LESSON = (
    "A common denominator lets you compare fractions directly. "
    "Rewrite each fraction so both share the same bottom number. "
    "Once the denominators match, the fraction with the larger numerator "
    "is the larger fraction. This works because you are now counting "
    "pieces of the same size."
)


def _engine(context=None, progress=None):
    engine = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    engine.session_contexts = {SESSION: context} if context else {}
    engine.active_scenes = {}
    engine.websocket_manager = None
    _SESSION_PROGRESS.pop(SESSION, None)
    if progress:
        _SESSION_PROGRESS[SESSION] = progress
    return engine


def _context(**overrides):
    fields = {
        "lesson_title": "Compare fractions",
        "lesson_content": LESSON,
        "learning_objective": "Compare fractions",
        "language_code": "en-US",
        "source_attributions": ["OpenStax Prealgebra, §4.2"],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _trigger():
    return Trigger(
        trigger_type=TriggerType.USER_ACTION,
        user_id="42",
        session_id=SESSION,
        action_data={"action_intent": ActionIntent.CONTINUE},
    )


def _texts(scene):
    return [
        c.text
        for c in scene.components
        if getattr(c, "type", None) == ComponentType.TEACHER_MESSAGE
    ]


def _intents(scene):
    return [
        getattr(c, "action_intent", None)
        for c in scene.components
        if getattr(c, "action_intent", None) is not None
    ]


class SafeFallbackTeachesTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def test_the_fallback_re_teaches_from_the_lesson_the_learner_is_in(self):
        engine = _engine(_context())

        scene = await engine._create_fallback_scene(_trigger())
        body = "\n".join(_texts(scene))

        # Actual teaching material, not an apology.
        self.assertIn("common denominator", body)
        self.assertIn("same bottom number", body)

    async def test_the_fallback_never_invents_teaching_material(self):
        """Generation just failed. This is the worst possible moment to make
        something up, so every taught sentence must come from the course."""
        engine = _engine(_context())

        scene = await engine._create_fallback_scene(_trigger())
        body = "\n".join(_texts(scene))

        taught = body.split("\n\n", 1)[1] if "\n\n" in body else ""
        self.assertTrue(taught)
        self.assertIn(taught.rstrip("…").strip(), LESSON)

    async def test_the_fallback_keeps_the_course_s_attribution(self):
        engine = _engine(_context())

        scene = await engine._create_fallback_scene(_trigger())

        attributions = [
            a
            for c in scene.components
            for a in (getattr(c, "source_attributions", None) or [])
        ]
        self.assertIn("OpenStax Prealgebra, §4.2", attributions)

    async def test_the_learner_is_offered_a_real_move_not_just_continue(self):
        """The old fallback's only exit was Continue, which led back to the
        same failure. A worked example is a request the engine can serve."""
        engine = _engine(_context())

        scene = await engine._create_fallback_scene(_trigger())
        intents = _intents(scene)

        self.assertIn(ActionIntent.REQUEST_EXAMPLE, intents)
        self.assertNotEqual(intents, [ActionIntent.CONTINUE])


class SafeFallbackDegradesTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def test_with_only_a_title_it_still_names_what_they_are_working_on(self):
        engine = _engine(_context(lesson_content=None))

        scene = await engine._create_fallback_scene(_trigger())
        body = "\n".join(_texts(scene))

        self.assertIn("Compare fractions", body)
        self.assertIn(ActionIntent.REQUEST_EXAMPLE, _intents(scene))

    async def test_with_nothing_at_all_it_asks_rather_than_dead_ending(self):
        """No context to teach from. Asking what they want to learn is a move
        that leads somewhere; a Continue button with nothing behind it is
        the dead end this replaces."""
        engine = _engine(context=None)

        scene = await engine._create_fallback_scene(_trigger())

        kinds = [getattr(c, "type", None) for c in scene.components]
        self.assertIn(ComponentType.INPUT_FIELD, kinds)
        self.assertIn(ActionIntent.ASK_QUESTION, _intents(scene))
        self.assertNotIn(ActionIntent.CONTINUE, _intents(scene))

    async def test_a_scene_is_always_produced(self):
        """This is the error path. A fallback that raises leaves the learner
        with the dead screen it exists to prevent."""
        for context in (None, _context(), _context(lesson_content=None),
                        _context(lesson_content="", lesson_title="", learning_objective="")):
            engine = _engine(context)
            scene = await engine._create_fallback_scene(_trigger())
            self.assertTrue(scene.components)

    async def test_spanish_sessions_stay_in_spanish(self):
        engine = _engine(_context(language_code="es-MX"))

        scene = await engine._create_fallback_scene(_trigger())
        body = "\n".join(_texts(scene))

        self.assertIn("Retomemos", body)


class ExcerptTests(unittest.TestCase):
    def test_a_short_lesson_is_used_whole(self):
        text = "A denominator is the bottom number of a fraction."
        self.assertEqual(
            SceneLifecycleEngine._excerpt_for_reteaching(text, 700), text
        )

    def test_a_long_lesson_is_cut_at_a_sentence_end(self):
        excerpt = SceneLifecycleEngine._excerpt_for_reteaching(LESSON, 120)
        self.assertTrue(excerpt.endswith("."))
        self.assertIn(excerpt, LESSON)

    def test_nothing_usable_returns_nothing(self):
        for value in (None, "", "   ", "too short"):
            self.assertIsNone(
                SceneLifecycleEngine._excerpt_for_reteaching(value, 700)
            )

    def test_an_excerpt_never_stops_mid_word(self):
        run_on = "word " * 400
        excerpt = SceneLifecycleEngine._excerpt_for_reteaching(run_on, 120)
        self.assertFalse(excerpt.rstrip("…").endswith("wor"))


class FallbackIsWiredToTheFailurePathTests(unittest.IsolatedAsyncioTestCase):
    """Asserting the fallback exists proves nothing if the failure path does
    not reach it, so this drives `process_trigger` with a Director that
    raises — the real shape of the failure."""

    def tearDown(self):
        _SESSION_PROGRESS.pop(SESSION, None)

    async def test_a_director_failure_still_teaches_the_learner(self):
        engine = _engine(_context())
        engine.context_assembler = MagicMock()
        engine.context_assembler.assemble_context = AsyncMock(
            return_value=_context(session_id=SESSION, course_complete=False)
        )
        engine.director = MagicMock()
        engine.director.decide_scene = AsyncMock(
            side_effect=RuntimeError("the model is down")
        )
        engine.compiler = MagicMock()
        engine._persist_session_progress = AsyncMock()

        scene = await engine.process_trigger(_trigger())
        body = "\n".join(_texts(scene))

        self.assertIn("common denominator", body)


if __name__ == "__main__":
    unittest.main()
