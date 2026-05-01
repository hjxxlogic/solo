from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from solo.project import ensure_project
from solo.workflow import load_workflows, status_data, work_items


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


class WorkflowLoadingTests(unittest.TestCase):
    def test_branch_workflow_overrides_global_by_file_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            global_dir = root / ".solo" / "global" / "workflows"
            branch_dir = root / ".solo" / "main" / "workflows"
            global_dir.mkdir(parents=True)
            branch_dir.mkdir(parents=True)
            (global_dir / "demo.yaml").write_text(
                yaml.safe_dump({"id": "demo", "title": "Global", "scope": {"type": "global"}}),
                encoding="utf-8",
            )
            (branch_dir / "demo.yaml").write_text(
                yaml.safe_dump({"id": "demo", "title": "Branch", "scope": {"type": "branch"}}),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflows = load_workflows(project)

            self.assertEqual(len(workflows), 1)
            self.assertEqual(workflows[0].title, "Branch")
            self.assertEqual(workflows[0].scope_type, "branch")

    def test_file_status_is_project_owned_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            status_dir = root / ".solo" / "global" / "status"
            workflow_dir.mkdir(parents=True)
            status_dir.mkdir(parents=True)
            (status_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "summary": {"total": 1},
                        "items": [{"id": "one", "title": "One", "status": "pending"}],
                    }
                ),
                encoding="utf-8",
            )
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "global"},
                        "status": {"type": "file", "path": ".solo/global/status/demo.yaml"},
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]

            self.assertEqual(status_data(project, workflow)["summary"]["total"], 1)
            items = work_items(project, workflow)
            self.assertEqual(items[0].external_id, "one")
            self.assertEqual(items[0].status, "pending")

    def test_branch_status_overrides_global_status_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            workflow_dir = root / ".solo" / "global" / "workflows"
            global_status_dir = root / ".solo" / "global" / "status"
            branch_status_dir = root / ".solo" / "main" / "status"
            workflow_dir.mkdir(parents=True)
            global_status_dir.mkdir(parents=True)
            branch_status_dir.mkdir(parents=True)
            (global_status_dir / "demo.yaml").write_text(
                yaml.safe_dump({"items": [{"id": "global", "title": "Global", "status": "pending"}]}),
                encoding="utf-8",
            )
            (branch_status_dir / "demo.yaml").write_text(
                yaml.safe_dump({"items": [{"id": "branch", "title": "Branch", "status": "done"}]}),
                encoding="utf-8",
            )
            (workflow_dir / "demo.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "demo",
                        "title": "Demo",
                        "scope": {"type": "global"},
                        "status": {"type": "file", "path": ".solo/global/status/demo.yaml"},
                    }
                ),
                encoding="utf-8",
            )

            project = ensure_project(root)
            workflow = load_workflows(project)[0]
            items = work_items(project, workflow)

            self.assertEqual(items[0].external_id, "branch")
            self.assertEqual(items[0].status, "done")


if __name__ == "__main__":
    unittest.main()
