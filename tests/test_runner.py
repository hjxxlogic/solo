from __future__ import annotations

import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml

from solo.project import ensure_project
from solo.runner import ActionRunner
from solo.store import Store
from solo.workflow import load_workflows


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


class ActionRunnerTests(unittest.TestCase):
    def test_command_action_records_run_log_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "global"},
                        "actions": [
                            {
                                "id": "hello",
                                "title": "Hello",
                                "runner": "command",
                                "cwd": "{projectRoot}",
                                "command": [
                                    "python3",
                                    "-c",
                                    "print('hello from workflow')",
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]
            runner = ActionRunner(project, Store(project.runtime_dir / "db.sqlite"))

            run = runner.run_sync(workflow, "hello")

            self.assertEqual(run.status, "completed")
            self.assertEqual(run.return_code, 0)
            self.assertIn("hello from workflow", run.log_path.read_text(encoding="utf-8"))
            self.assertIsNotNone(runner.get_run(run.id))

    def test_dry_run_does_not_execute_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            workflow_dir.mkdir(parents=True)
            marker = root / "marker.txt"
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "global"},
                        "actions": [
                            {
                                "id": "write",
                                "runner": "command",
                                "cwd": "{projectRoot}",
                                "command": ["python3", "-c", "open('marker.txt', 'w').write('x')"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]
            runner = ActionRunner(project, Store(project.runtime_dir / "db.sqlite"))

            run = runner.run_sync(workflow, "write", dry_run=True)

            self.assertEqual(run.status, "dry_run")
            self.assertFalse(marker.exists())

    def test_action_can_create_worktree_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "worktree"},
                        "actions": [
                            {
                                "id": "wt",
                                "runner": "command",
                                "cwd": "{scopePath}",
                                "worktree": {
                                    "mode": "create",
                                    "baseRef": "main",
                                    "branchName": "solo/{runId}",
                                    "path": ".solo-runtime/worktrees/{runId}",
                                },
                                "command": ["python3", "-c", "open('created.txt', 'w').write('ok')"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]
            runner = ActionRunner(project, Store(project.runtime_dir / "db.sqlite"))

            run = runner.run_sync(workflow, "wt")

            self.assertEqual(run.status, "completed")
            self.assertTrue(run.cwd.match("*/.solo-runtime/worktrees/*"))
            self.assertTrue((run.cwd / "created.txt").exists())

    def test_running_action_can_be_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "global"},
                        "actions": [
                            {
                                "id": "sleep",
                                "runner": "command",
                                "cwd": "{projectRoot}",
                                "command": ["python3", "-c", "import time; time.sleep(30)"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]
            runner = ActionRunner(project, Store(project.runtime_dir / "db.sqlite"))
            result: dict[str, object] = {}

            thread = threading.Thread(target=lambda: result.update(run=runner.run_sync(workflow, "sleep")))
            thread.start()
            deadline = time.time() + 5
            run_id = None
            while time.time() < deadline:
                runs = runner.store.list_runs(project.id)
                if runs and runs[0]["status"] == "running":
                    run_id = runs[0]["id"]
                    break
                time.sleep(0.05)
            self.assertIsNotNone(run_id)

            stopped = runner.stop_run(str(run_id))
            thread.join(timeout=5)

            self.assertEqual(stopped.status, "stopped")
            self.assertFalse(thread.is_alive())
            self.assertEqual(runner.get_run(str(run_id)).status, "stopped")


if __name__ == "__main__":
    unittest.main()
