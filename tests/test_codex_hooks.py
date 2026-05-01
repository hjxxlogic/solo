from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from solo.codex_hook import main as hook_main
from solo.init import install_codex_hooks
from solo.project import ensure_project
from solo.store import Store


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


class CodexHookTests(unittest.TestCase):
    def test_init_installs_project_codex_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            project = ensure_project(root)

            result = install_codex_hooks(project)

            config = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
            hooks = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(result["events"], ["SessionStart", "UserPromptSubmit", "Stop"])
            self.assertIn("codex_hooks = true", config)
            for event in result["events"]:
                command = hooks["hooks"][event][0]["hooks"][0]["command"]
                self.assertIn("solo.codex_hook", command)
                self.assertIn(f"--event {event}", command)
                self.assertIn(f"--repo {root}", command)

    def test_hook_records_first_prompt_and_end_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            project = ensure_project(root)
            payload = {
                "session_id": "session-one",
                "cwd": str(root),
                "prompt": " ".join(["hello"] * 30),
            }

            with patch("sys.stdin", io.StringIO(json.dumps(payload))):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        hook_main(["--event", "UserPromptSubmit", "--repo", str(root)]),
                        0,
                    )
            with patch("sys.stdin", io.StringIO(json.dumps({"session_id": "session-one"}))):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(hook_main(["--event", "Stop", "--repo", str(root)]), 0)

            store = Store(project.runtime_dir / "db.sqlite")
            sessions = store.list_codex_sessions(project.id)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["id"], "session-one")
            self.assertEqual(sessions[0]["status"], "ended")
            self.assertTrue(sessions[0]["ended"])
            self.assertEqual(len(sessions[0]["firstPrompt"]), 80)
            self.assertEqual(sessions[0]["turnCount"], 1)


if __name__ == "__main__":
    unittest.main()
