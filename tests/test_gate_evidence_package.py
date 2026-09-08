from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.gate_evidence_package import _run_promotion_dual_review


class PromotionReviewExitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.script = scripts / "run_dual_review_pipeline.py"
        self.script.write_text(
            "import os, signal, sys\n"
            "from pathlib import Path\n"
            "code = Path(sys.argv[sys.argv.index('--from-evidence') + 1]).stem\n"
            "with Path('calls').open('a') as log: log.write(code + '\\n')\n"
            "if code == 'signal': os.kill(os.getpid(), signal.SIGTERM)\n"
            "raise SystemExit(int(code))\n",
            encoding="utf-8",
        )

    def review(self, codes: tuple[str, ...], *, skip: str = "") -> int:
        # This is a real local Python child process, with synthetic exit behavior
        # only. It never imports AIAuditBridge, reads evidence or calls a model.
        with patch.dict(os.environ, {"AIAUDIT_BRIDGE_ROOT": str(self.root), "DUAL_REVIEW_GATE_SKIP": skip}):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return _run_promotion_dual_review([self.root / f"{code}.json" for code in codes])

    def test_every_nonzero_exit_blocks_promotion(self) -> None:
        for code in ("1", "2", "3", "127", "signal"):
            with self.subTest(code=code):
                self.assertEqual(self.review((code,)), 1)

    def test_failure_remains_blocking_after_later_success(self) -> None:
        for failure in ("1", "2", "signal"):
            with self.subTest(failure=failure):
                (self.root / "calls").write_text("", encoding="utf-8")
                self.assertEqual(self.review((failure, "0")), 1)
                self.assertEqual((self.root / "calls").read_text().splitlines(), [failure, "0"])

    def test_all_successful_reviews_pass(self) -> None:
        self.assertEqual(self.review(("0", "0")), 0)
        self.assertEqual((self.root / "calls").read_text().splitlines(), ["0", "0"])

    def test_explicit_skip_does_not_run_review(self) -> None:
        self.assertEqual(self.review(("1",), skip="true"), 0)
        self.assertFalse((self.root / "calls").exists())

    def test_missing_optional_script_keeps_existing_skip(self) -> None:
        self.script.unlink()
        self.assertEqual(self.review(("1",)), 0)
        self.assertFalse((self.root / "calls").exists())


if __name__ == "__main__":
    unittest.main()
