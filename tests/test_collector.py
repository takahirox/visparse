from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from visparse import ValidationError, build_dna, compare_design, render_design, validate_inspection
from visparse_collector.browser import CaptureOptions, capture, validate_url


class CollectorConfigurationTests(unittest.TestCase):
    def test_rejects_non_http_credentials_and_invalid_limits_before_browser(self):
        for url in ("file:///etc/hosts", "javascript:alert(1)", "https://user:password@example.invalid", "https:///missing"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_url(url)
        for options in (CaptureOptions(viewports=()), CaptureOptions(viewports=((0, 900),)), CaptureOptions(max_nodes=0),
                        CaptureOptions(timeout_seconds=float("nan")), CaptureOptions(viewports=((10, 10), (10, 10)))):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                options.validate()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get("VISPARSE_BROWSER_TESTS") == "1", "set VISPARSE_BROWSER_TESTS=1 with Chromium installed")
class BrowserIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(Path(__file__).parent / "fixtures"))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/collector.html"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_real_browser_capture_normalize_render_compare(self):
        with TemporaryDirectory() as directory:
            bundle = capture(self.url, directory)
            validate_inspection(bundle)
            self.assertEqual(len(bundle["captures"]), 6)
            serialized = json.dumps(bundle)
            for private in ("fixture-private-value", "fixture-password-value", "fixture-private-note"):
                self.assertNotIn(private, serialized)
            for shot in [c for c in bundle["captures"] if c["kind"] == "screenshot"]:
                path = Path(directory) / shot["payload"]["artifact_file"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), shot["payload"]["sha256"])
            ax = [c for c in bundle["captures"] if c["kind"] == "accessibility"]
            self.assertTrue(any(n["role"] == "button" and n["name"] == "Create project" for c in ax for n in c["payload"]["nodes"]))
            value = build_dna(inspection=bundle)
            headings = {f["scope"]["viewport"]: f["value"] for f in value["features"] if f["name"] == "typography.font_size" and f["scope"]["subject"] == "visible-sample:tag=h1"}
            self.assertEqual(headings, {"1440x900": 48, "390x844": 32})
            self.assertIn("typography.font_size", render_design(value))
            self.assertEqual(compare_design(value, value)["dimensions"]["typography"]["score"], 1)

    def test_sampling_limits_are_reported(self):
        with TemporaryDirectory() as directory:
            bundle = capture(self.url, directory, CaptureOptions(viewports=((390, 844),), max_nodes=2))
            dom = next(c for c in bundle["captures"] if c["kind"] == "dom")
            self.assertTrue(dom["payload"]["coverage"]["truncated"])
            self.assertEqual(len(dom["payload"]["nodes"]), 2)


if __name__ == "__main__":
    unittest.main()
