"""Fail-closed safety checks for manual provider-backed staging validation."""
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
