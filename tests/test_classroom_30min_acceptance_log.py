"""The classroom manual QA journal must not claim a short/incomplete run passed."""

import unittest

from scripts.classroom_30min_acceptance_log import REQUIRED, summarize


def _rows(elapsed, include_all=True, failed=False):
    rows = [{"type": "start", "epoch": 1000.0}]
    kinds = REQUIRED if include_all else REQUIRED[:2]
    rows += [
        {"type": "event", "kind": kind, "status": "pass"}
        for kind in kinds
    ]
    if failed:
        rows.append({"type": "event", "kind": "teacher_audio", "status": "fail"})
    rows.append({"type": "finish", "epoch": 1000.0 + elapsed})
    return rows


class AcceptanceJournalTests(unittest.TestCase):
    def test_short_run_cannot_pass_with_every_required_event(self):
        result = summarize(_rows(59))
        self.assertEqual(result["automated_gate"], "INCOMPLETE")
        self.assertFalse(result["thirty_minutes_observed"])

    def test_thirty_minutes_without_checkpoints_cannot_pass(self):
        result = summarize(_rows(1801, include_all=False))
        self.assertEqual(result["automated_gate"], "INCOMPLETE")
        self.assertIn("guided_wrong", result["missing_required_checks"])

    def test_thirty_minutes_with_complete_evidence_passes_structural_gate_only(self):
        result = summarize(_rows(1800))
        self.assertEqual(result["automated_gate"], "PASS")
        self.assertTrue(result["human_listening_review_required"])

    def test_explicit_failure_blocks_pass_even_after_thirty_minutes(self):
        result = summarize(_rows(1800, failed=True))
        self.assertEqual(result["automated_gate"], "INCOMPLETE")
        self.assertEqual(result["explicit_failures"], 1)
