"""Offline validation of the opt-in ONNX bilingual voice QA harness."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "onnx_voice_quality_check.py"
spec = importlib.util.spec_from_file_location("onnx_voice_quality_check", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class _Response:
    status = 200
    headers = {"Content-Type": "audio/mpeg"}

    def __init__(self):
        self._payload = b"ID3" + b"\0" * 1200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n):
        result, self._payload = self._payload[:n], self._payload[n:]
        return result


class VoiceQATests(unittest.TestCase):
    def test_five_cases_cover_both_languages_and_cast(self):
        cases = module.VOICE_SAMPLES
        self.assertEqual(len(cases), 5)
        self.assertEqual({case["locale"][:2] for case in cases}, {"en", "es"})
        self.assertEqual({case["voice"] for case in cases}, {"af_heart", "am_liam", "ef_dora"})
        self.assertTrue(any("third" in case["input"] for case in cases))
        self.assertTrue(any("tercio" in case["input"] for case in cases))
        self.assertTrue(any("¿" in case["input"] for case in cases))

    def test_request_and_metadata_report_is_opt_in(self):
        captured = []

        def fake_urlopen(request, timeout):
            captured.append((request.full_url, json.loads(request.data), timeout))
            return _Response()

        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            with patch.object(module.urllib.request, "urlopen", fake_urlopen), patch.object(
                module, "_probe", lambda path: {"probe_available": False}
            ):
                sample = module.VOICE_SAMPLES[3]
                outcome = module.check_sample("http://pilot.internal/", sample, tmp_path, timeout=10)
            self.assertTrue(outcome["metadata_pass"])
            self.assertEqual(outcome["bytes"], 1203)
            self.assertTrue((tmp_path / "es_welcome.mp3").is_file())

        url, body, timeout = captured[0]
        self.assertEqual(url, "http://pilot.internal/v1/audio/speech")
        self.assertEqual(timeout, 10)
        self.assertEqual(body, {
            "model": "kokoro", "input": sample["input"], "voice": "ef_dora",
            "lang": "es-es", "response_format": "mp3", "speed": 1.0,
            "stream": True,
        })

    def test_non_audio_content_fails_gate(self):
        class _WrongType(_Response):
            headers = {"Content-Type": "text/html"}

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(module.urllib.request, "urlopen", lambda *args, **kw: _WrongType()), patch.object(
                module, "_probe", lambda path: {"probe_available": False}
            ):
                result = module.check_sample(
                    "http://pilot.internal", module.VOICE_SAMPLES[0], Path(temporary), 10
                )
            self.assertFalse(result["metadata_pass"])


if __name__ == "__main__":
    unittest.main()
