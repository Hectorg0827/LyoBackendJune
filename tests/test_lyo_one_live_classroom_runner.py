"""Fail-closed safety checks for manual provider-backed staging validation."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


RUNNER = Path(__file__).resolve().parents[1] / "scripts/validate_lyo_one_live_classroom.py"
spec = importlib.util.spec_from_file_location("lyo_one_staging_teacher", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class IsolatedTeacherSafetyTests(unittest.TestCase):
    def test_rejects_production_or_arbitrary_endpoints(self):
        with patch.dict(os.environ, {"LYO_ONE_PROVIDER_STAGING_READY": "yes"}):
            for url in (
                "https://api.lyoai.app",
                "http://lyojourneystagingbackend-staging.up.railway.app",
                "https://lyojourneystagingbackend-staging.up.railway.app.evil.test",
                "https://user:pw@lyojourneystagingbackend-staging.up.railway.app",
                "https://lyojourneystagingbackend-staging.up.railway.app/other",
            ):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    runner.require_safe_target(url)

    def test_explicit_provider_readiness_required(self):
        with patch.dict(os.environ, {"LYO_ONE_PROVIDER_STAGING_READY": "no"}):
            with self.assertRaises(ValueError):
                runner.require_safe_target()
        with patch.dict(os.environ, {"LYO_ONE_PROVIDER_STAGING_READY": "yes"}):
            runner.require_safe_target()

    def test_synthetic_registration_never_uses_a_production_host(self):
        self.assertEqual(runner.EXPECTED_HOST, "lyojourneystagingbackend-staging.up.railway.app")
        self.assertNotEqual(runner.STAGING_API, "https://api.lyoai.app")
        self.assertTrue(runner.STAGING_API.startswith("https://"))


class ProviderCandidateTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "LYO_ONE_PROVIDER_STAGING_READY": "yes",
            "LYO_ONE_EXPECTED_BACKEND_SHA": "a" * 40,
        })
        env.start()
        self.addCleanup(env.stop)

    def health(self, *, sha="a" * 40, configured=True, environment="staging"):
        return io.BytesIO(json.dumps({"environment": environment, "commit_sha": sha,
            "services": {"ai": {"models": {"gemini-2.5-flash": {"configured": configured}}}}}).encode())

    def test_missing_provider_stops_before_creating_learners_or_running_teaching(self):
        with patch.object(runner.urllib.request, "urlopen", return_value=self.health(configured=False)), \
                patch.object(runner, "create_synthetic_access_token") as register, \
                patch.object(runner.subprocess, "run") as teach, \
                self.assertRaisesRegex(RuntimeError, "no configured Gemini"):
            runner.main()
        register.assert_not_called()
        teach.assert_not_called()

    def test_healthy_previous_revision_cannot_validate_this_candidate(self):
        with patch.object(runner.urllib.request, "urlopen", return_value=self.health(sha="b" * 40)), \
                self.assertRaisesRegex(RuntimeError, "candidate mismatch"):
            runner.verify_candidate()

    def test_a_production_environment_cannot_satisfy_the_isolated_gate(self):
        with patch.object(runner.urllib.request, "urlopen", return_value=self.health(environment="production")), \
                self.assertRaisesRegex(RuntimeError, "candidate mismatch"):
            runner.verify_candidate()

    def test_partial_candidate_sha_is_rejected_before_network_access(self):
        with patch.dict(os.environ, {"LYO_ONE_EXPECTED_BACKEND_SHA": "aaaaaaa"}), \
                patch.object(runner.urllib.request, "urlopen") as network, \
                self.assertRaisesRegex(ValueError, "full deployed candidate"):
            runner.verify_candidate()
        network.assert_not_called()

    def test_preflight_records_the_real_revision_and_configured_gemini_models(self):
        with patch.object(runner.urllib.request, "urlopen", return_value=self.health()):
            result = runner.verify_candidate()
        self.assertEqual(result, {"commit_sha": "a" * 40,
                                  "configured_gemini_models": ["gemini-2.5-flash"]})



class TeachingEvidenceRegressionTests(unittest.TestCase):
    """A stream of server fallback cards must never count as a passed lesson."""

    def test_recovery_notice_is_not_a_lesson(self):
        from scripts.live_teacher_quality import (
            has_authored_classroom_instruction, is_recovery_only_scene,
        )
        scene = {
            "metadata": {"presentation_focus": "recovery", "teaching_action": None},
            "components": [
                {"type": "TeacherMessage", "text": "Let's stay with fractions."},
                {"type": "ExampleBlock", "component_id": "classroom-recovery/notice",
                 "content": "Your lesson is paused"},
                {"type": "CTAButton", "action_intent": "retry"},
            ],
        }
        self.assertTrue(is_recovery_only_scene(scene))
        self.assertFalse(has_authored_classroom_instruction(scene))

    def test_real_teaching_is_distinguished_from_recovery_and_empty_ui(self):
        from scripts.live_teacher_quality import (
            has_authored_classroom_instruction, is_recovery_only_scene,
        )
        authored = {"metadata": {"teaching_action": "EXPLAIN"},
                    "components": [{"type": "TeacherMessage",
                                    "text": "Because each whole is divided into equal parts."}]}
        empty = {"metadata": {}, "components": [{"type": "TeacherMessage", "text": "Please retry"}]}
        self.assertFalse(is_recovery_only_scene(authored))
        self.assertTrue(has_authored_classroom_instruction(authored))
        self.assertFalse(has_authored_classroom_instruction(empty))

    def test_recovery_overlay_cannot_masquerade_as_valid_instruction(self):
        from scripts.live_teacher_quality import has_authored_classroom_instruction
        mixed = {"metadata": {"teaching_action": "EXPLAIN"},
                 "components": [
                     {"type": "TeacherMessage", "text": "Lesson"},
                     {"type": "ExampleBlock", "component_id": "classroom-recovery/notice",
                      "content": "Retry"},
                 ]}
        self.assertFalse(has_authored_classroom_instruction(mixed))


if __name__ == "__main__":
    unittest.main()
