"""A healthy previous deployment cannot satisfy the candidate's staging gate."""

import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


RUNNER = Path(__file__).resolve().parents[1] / "scripts/validate_lyo_one_staging_http.py"
spec = importlib.util.spec_from_file_location("lyo_one_revision_gate", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
BACKEND = "a" * 40
CLIENT = "b" * 40


class StagingRevisionGateTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "LYO_ONE_STAGING_SMOKE": "1",
            "LYO_ONE_EXPECTED_BACKEND_SHA": BACKEND,
            "LYO_ONE_EXPECTED_CLIENT_SHA": CLIENT,
        })
        env.start()
        self.addCleanup(env.stop)

    def test_expected_pair_is_verified_against_both_live_health_endpoints(self):
        response = io.BytesIO(json.dumps({"commit": CLIENT}).encode())
        with patch.object(runner, "http", return_value=(200, {"commit_sha": BACKEND})) as backend, \
                patch.object(runner.urllib.request, "urlopen", return_value=response) as web:
            runner.verify_deployed_revisions()
        backend.assert_called_once_with("/health")
        self.assertEqual(web.call_args.args[0].full_url, runner.STAGING_WEB + "/api/health")

    def test_healthy_previous_backend_is_rejected_before_testing_learners(self):
        with patch.object(runner, "http", return_value=(200, {"commit_sha": "c" * 40})), \
                self.assertRaisesRegex(AssertionError, "Backend revision mismatch"):
            runner.verify_deployed_revisions()

    def test_missing_backend_revision_does_not_count_as_a_match(self):
        with patch.object(runner, "http", return_value=(200, {"status": "healthy"})), \
                self.assertRaisesRegex(AssertionError, "Backend revision mismatch"):
            runner.verify_deployed_revisions()

    def test_healthy_previous_client_is_rejected(self):
        response = io.BytesIO(json.dumps({"commit": "c" * 40}).encode())
        with patch.object(runner, "http", return_value=(200, {"commit_sha": BACKEND})), \
                patch.object(runner.urllib.request, "urlopen", return_value=response), \
                self.assertRaisesRegex(AssertionError, "Client revision mismatch"):
            runner.verify_deployed_revisions()

    def test_partial_or_invalid_revision_is_rejected(self):
        for name in ("LYO_ONE_EXPECTED_BACKEND_SHA", "LYO_ONE_EXPECTED_CLIENT_SHA"):
            for value in ("", "main", "a" * 7, "g" * 40):
                with self.subTest(name=name, value=value), \
                        patch.dict(os.environ, {name: value}), \
                        self.assertRaisesRegex(RuntimeError, "full commit SHA"):
                    runner.require_staging()

    def test_valid_revision_inputs_keep_the_isolated_host_guard(self):
        runner.require_staging()
        with patch.object(runner, "BASE", "https://api.lyoai.app"), \
                self.assertRaisesRegex(RuntimeError, "non-isolated domain"):
            runner.require_staging()


if __name__ == "__main__":
    unittest.main()
