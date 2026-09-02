from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from test_design import profile  # noqa: E402
from visparse.cli import main  # noqa: E402
from visparse.design import normalize_design_profile  # noqa: E402


class CliDesignTests(unittest.TestCase):
    def test_single_reference_screenshot(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reference.png"
            path.write_bytes(b"reference")
            analyzer = Mock()
            analyzer.analyze.side_effect = lambda references, targets: profile(list(references), list(targets))
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.cli.CodexDesignAnalyzer", return_value=analyzer), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["analyze-design", str(path)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        references, targets = analyzer.analyze.call_args.args
        self.assertEqual([item.id for item in references], ["reference-1"])
        self.assertEqual(list(targets), [])

    def test_single_and_multiple_screenshots_with_target(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "desktop.png", root / "mobile.png", root / "target.png"]
            for index, path in enumerate(paths):
                path.write_bytes(f"image-{index}".encode())
            captured = []
            analyzer = Mock()
            analyzer.analyze.side_effect = lambda references, targets: (
                captured.append((list(references), list(targets))),
                profile(list(references), list(targets)),
            )[1]
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.cli.CodexDesignAnalyzer", return_value=analyzer), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = main([
                    "analyze-design", str(paths[0]), str(paths[1]),
                    "--target", str(paths[2]),
                ])

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        references, targets = captured[0]
        self.assertEqual([item.id for item in references], ["reference-1", "reference-2"])
        self.assertEqual([item.id for item in targets], ["target-1"])
        self.assertEqual(stdout.getvalue(), normalize_design_profile(profile(references, targets)))

    def test_invalid_input_skips_design_analyzer(self) -> None:
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.png"
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("visparse.cli.CodexDesignAnalyzer") as analyzer, \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["analyze-design", str(missing)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("source path is not a regular file", stderr.getvalue())
        analyzer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
