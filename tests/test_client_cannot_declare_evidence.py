"""A client may say what it did. It may not say what that proved.

`POST /api/v1/evolution/events` takes a `LearningEventCreate` straight from an
authenticated client, and that schema carries `evidence_type`,
`evidence_confidence`, `measurable_outcome` and `skill_ids_json`.

So a learner's device could post itself a transfer demonstration at full
confidence, or ask the event processor to run a DKT update on a skill it
names, and the learner model would believe all of it. That is the exact thing
the check endpoint exists to prevent when it grades from a stored block rather
than from what the client claims happened — the same rule, missing from the
door next to it.
"""

import unittest
from pathlib import Path

from lyo_app.events.evidence import (
    SOURCE_SURFACES,
    derive_mastery_state,
    sanitize_client_event,
)
from lyo_app.events.models import EventType
from lyo_app.events.schemas import LearningEventCreate

ROOT = Path(__file__).resolve().parents[1]


def _claim(**overrides):
    """What a client would send if it wanted to promote itself."""
    fields = {
        "user_id": 1,
        "event_type": EventType.QUIZ_ANSWER,
        "concept_id": "quantum_mechanics",
        "evidence_type": "transfer",
        "evidence_confidence": 1.0,
        "measurable_outcome": 1.0,
        "skill_ids_json": ["quantum_mechanics"],
        "source_surface": "chat",
    }
    fields.update(overrides)
    return LearningEventCreate(**fields)


class WhatIsRefusedTests(unittest.TestCase):
    def test_a_client_cannot_award_itself_a_rung(self):
        self.assertEqual(sanitize_client_event(_claim()).evidence_type, "exposure")

    def test_a_client_cannot_award_itself_confidence(self):
        self.assertEqual(sanitize_client_event(_claim()).evidence_confidence, 0.0)

    def test_a_client_cannot_declare_itself_correct(self):
        """`measurable_outcome` is the graded result. It is the server's."""
        self.assertIsNone(sanitize_client_event(_claim()).measurable_outcome)

    def test_a_client_cannot_ask_for_a_mastery_update(self):
        """`skill_ids_json` is what asks the processor to run DKT."""
        self.assertIsNone(sanitize_client_event(_claim()).skill_ids_json)

    def test_an_unrecognised_surface_is_dropped_not_stored(self):
        self.assertIsNone(sanitize_client_event(_claim(source_surface="admin")).source_surface)

    def test_no_amount_of_posting_reaches_mastery(self):
        """The end-to-end claim: a client that posts the strongest evidence it
        can name, repeatedly, still has not demonstrated anything."""
        posted = [sanitize_client_event(_claim()) for _ in range(50)]
        state = derive_mastery_state(
            [{"kind": e.evidence_type, "confidence": e.evidence_confidence} for e in posted]
        )
        self.assertEqual(state, "EXPOSED")


class WhatIsKeptTests(unittest.TestCase):
    def test_the_learner_still_gets_credit_for_meeting_the_concept(self):
        """Exposure is real: they encountered it. It just proves nothing on
        its own, which is what the ladder says it means."""
        event = sanitize_client_event(_claim())
        self.assertEqual(event.concept_id, "quantum_mechanics")
        self.assertEqual(event.evidence_type, "exposure")

    def test_an_event_naming_no_concept_carries_no_rung_at_all(self):
        event = sanitize_client_event(_claim(concept_id=None))
        self.assertIsNone(event.evidence_type)
        self.assertIsNone(event.evidence_confidence)

    def test_hints_and_misconceptions_survive(self):
        """Neither can flatter a learner: one only damps confidence, the other
        is a note about an error."""
        event = sanitize_client_event(_claim(hints_used=3, misconception="sign_error"))
        self.assertEqual(event.hints_used, 3)
        self.assertEqual(event.misconception, "sign_error")

    def test_a_known_surface_is_preserved(self):
        for surface in SOURCE_SURFACES:
            self.assertEqual(
                sanitize_client_event(_claim(source_surface=surface)).source_surface,
                surface,
            )

    def test_the_event_type_is_still_the_clients_to_report(self):
        event = sanitize_client_event(_claim(event_type=EventType.LESSON_COMPLETION))
        self.assertEqual(event.event_type, EventType.LESSON_COMPLETION)


class TheDoorIsActuallyGuardedTests(unittest.TestCase):
    """Sanitising correctly is worth nothing if the route does not call it."""

    def setUp(self):
        source = (ROOT / "lyo_app" / "evolution" / "routes.py").read_text()
        start = source.index("async def log_event(")
        rest = source[start:]
        ends = [i for i in (rest.find("\n@router"), rest.find("\n# ──")) if i != -1]
        self.body = rest[: min(ends)] if ends else rest

    def test_the_endpoint_sanitises_before_logging(self):
        self.assertIn("sanitize_client_event(event)", self.body)

    def test_the_raw_event_is_not_logged(self):
        self.assertNotIn("log_learning_event(db, event)", self.body)

    def test_the_user_id_is_still_taken_from_the_token(self):
        self.assertIn("event.user_id = user.id", self.body)


if __name__ == "__main__":
    unittest.main()
