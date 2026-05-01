from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from solo.app import SoloContext, create_app
from solo.project import ensure_project


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


class ProjectRuntimeTests(unittest.TestCase):
    def test_runtime_dir_is_scoped_by_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)

            project = ensure_project(root)

            self.assertEqual(project.runtime_dir, root / ".solo-runtime" / "projects" / project.id)
            self.assertTrue((project.runtime_dir / "prompts").is_dir())
            self.assertTrue((project.runtime_dir / "logs").is_dir())
            self.assertTrue((project.runtime_dir / "worktrees").is_dir())
            self.assertTrue((project.runtime_dir / "editors").is_dir())
            self.assertEqual(project.to_dict()["runtimeDir"], f".solo-runtime/projects/{project.id}")

    def test_different_startup_projects_get_different_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            root_a.mkdir()
            root_b.mkdir()
            init_repo(root_a)
            init_repo(root_b)

            ctx_a = SoloContext(root_a)
            ctx_b = SoloContext(root_b)

            self.assertNotEqual(ctx_a.project.id, ctx_b.project.id)
            self.assertNotEqual(ctx_a.project.runtime_dir, ctx_b.project.runtime_dir)
            self.assertNotEqual(ctx_a.store.db_path, ctx_b.store.db_path)

    def test_project_qualified_api_uses_startup_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            project = ensure_project(root)

            client = TestClient(create_app(root))
            project_response = client.get(f"/api/projects/{project.id}")
            runs = client.get(f"/api/projects/{project.id}/runs")
            missing = client.get("/api/projects/not-a-project/runs")

            self.assertEqual(project_response.status_code, 200)
            self.assertEqual(project_response.json()["id"], project.id)
            self.assertEqual(runs.status_code, 200)
            self.assertEqual(runs.json(), [])
            self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
