from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from solo.app import SoloContext
from solo.ui import render_index


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    (root / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=solo",
            "-c",
            "user.email=solo@example.invalid",
            "commit",
            "-m",
            "init",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )


class UiRenderingTests(unittest.TestCase):
    def test_index_is_rendered_with_jinja_bootstrap_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)

            html = render_index(SoloContext(root))

            self.assertIn("<!doctype html>", html)
            self.assertIn("window.SOLO_BOOTSTRAP", html)
            self.assertIn(str(root), html)
            self.assertIn("/static/app.js", html)
            self.assertIn('data-theme="light"', html)
            self.assertIn('data-theme-choice="light"', html)
            self.assertIn('data-theme-choice="dark"', html)
            self.assertIn("solo-theme", html)
            self.assertNotIn('id="projectSelect"', html)
            self.assertNotIn('id="projectDialog"', html)
            self.assertIn('id="initProjectButton"', html)
            self.assertIn('id="sessionsBody"', html)
            self.assertIn('id="navSessionCount"', html)
            self.assertIn('id="editorOverlay"', html)
            self.assertIn('id="editorBackButton"', html)
            self.assertIn('id="editorFrame"', html)


if __name__ == "__main__":
    unittest.main()
