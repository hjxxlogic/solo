from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import git
from .errors import ValidationError
from .models import Project


def project_id_for(root: Path) -> str:
    digest = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()
    return digest[:16]


def project_runtime_dir(root: Path) -> Path:
    root = root.resolve()
    return root / ".solo-runtime" / "projects" / project_id_for(root)


def ensure_project(root: Path) -> Project:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValidationError(f"project root does not exist or is not a directory: {root}")
    if not git.is_git_repo(root):
        raise ValidationError(f"project root is not a git repository root: {root}")

    active = git.active_branch(root)
    default = git.default_branch(root)
    global_config_dir = root / ".solo" / "global"
    active_config_dir = root / ".solo" / active if active else None
    workflow_dirs = [global_config_dir / "workflows"]
    if active_config_dir is not None:
        workflow_dirs.append(active_config_dir / "workflows")

    runtime_dir = project_runtime_dir(root)
    for subdir in (
        runtime_dir,
        runtime_dir / "prompts",
        runtime_dir / "logs",
        runtime_dir / "worktrees",
        runtime_dir / "editors",
    ):
        subdir.mkdir(parents=True, exist_ok=True)

    return Project(
        id=project_id_for(root),
        name=root.name,
        root_path=root,
        default_branch=default,
        active_branch=active,
        global_config_dir=global_config_dir,
        active_config_dir=active_config_dir if active_config_dir and active_config_dir.exists() else None,
        effective_workflow_dirs=tuple(workflow_dirs),
        runtime_dir=runtime_dir,
    )


def git_info(project: Project) -> dict:
    return {
        "branch": project.active_branch,
        "defaultBranch": project.default_branch,
        "dirty": git.dirty_status(project.root_path),
        "worktrees": git.worktrees(project.root_path),
    }


def write_runtime_json(project: Project, name: str, data: dict) -> Path:
    path = project.runtime_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
