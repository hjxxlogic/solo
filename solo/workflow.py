from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .errors import NotFoundError, ValidationError
from .models import JsonDict, Project, WorkItem, Workflow, now_iso


def _load_yaml(path: Path) -> JsonDict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"YAML file must contain an object: {path}")
    return data


def _workflow_files(project: Project) -> list[Path]:
    by_name: dict[str, Path] = {}
    for directory in project.effective_workflow_dirs:
        if not directory.exists():
            continue
        for pattern in ("*.yaml", "*.yml"):
            for path in sorted(directory.glob(pattern)):
                by_name[path.stem] = path
    return list(by_name.values())


def load_workflows(project: Project) -> list[Workflow]:
    workflows: list[Workflow] = []
    for path in _workflow_files(project):
        data = _load_yaml(path)
        workflow_id = str(data.get("id") or path.stem)
        scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
        scope_type = str(scope.get("type") or "global")
        if scope_type not in {"global", "branch", "worktree"}:
            raise ValidationError(f"unknown workflow scope type in {path}: {scope_type}")
        workflows.append(
            Workflow(
                id=workflow_id,
                project_id=project.id,
                title=str(data.get("title") or workflow_id),
                description=str(data.get("description") or ""),
                definition_path=path,
                scope_type=scope_type,
                status=data.get("status") if isinstance(data.get("status"), dict) else {},
                actions=data.get("actions") if isinstance(data.get("actions"), list) else [],
                views=data.get("views") if isinstance(data.get("views"), list) else [],
                raw=data,
            )
        )
    return workflows


def find_workflow(project: Project, workflow_id: str) -> Workflow:
    for workflow in load_workflows(project):
        if workflow.id == workflow_id:
            return workflow
    raise NotFoundError(f"workflow not found: {workflow_id}")


def find_action(workflow: Workflow, action_id: str) -> JsonDict:
    for action in workflow.actions:
        if str(action.get("id")) == action_id:
            return action
    raise NotFoundError(f"action not found: {workflow.id}/{action_id}")


def status_data(project: Project, workflow: Workflow) -> JsonDict:
    status = workflow.status
    status_type = str(status.get("type") or "")
    if status_type == "file":
        path = resolve_project_path(project, str(status.get("path") or ""))
        if not path.exists():
            return _empty_status()
        return _load_yaml(path)
    if status_type == "command":
        command = status.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValidationError(f"status.command must be a string list for workflow {workflow.id}")
        cwd = resolve_template_path(project, str(status.get("cwd") or "{projectRoot}"), workflow, None)
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise ValidationError(
                f"status command failed for workflow {workflow.id}: {result.stderr.strip()}"
            )
        try:
            parsed = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError(f"status command did not return JSON for {workflow.id}") from exc
        if not isinstance(parsed, dict):
            raise ValidationError(f"status command must return an object for {workflow.id}")
        return parsed
    return _empty_status()


def work_items(project: Project, workflow: Workflow) -> list[WorkItem]:
    data = status_data(project, workflow)
    items = data.get("items") or data.get("results") or []
    if not isinstance(items, list):
        return []
    now = now_iso()
    output: list[WorkItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        external_id = str(item.get("id") or item.get("name") or len(output))
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        output.append(
            WorkItem(
                id=f"{workflow.id}:{external_id}",
                workflow_id=workflow.id,
                external_id=external_id,
                title=str(item.get("title") or item.get("name") or external_id),
                status=str(item.get("status") or "unknown"),
                scope_type=str(scope.get("type") or workflow.scope_type),
                scope_ref=scope.get("ref"),
                source_path=item.get("sourcePath") or item.get("path") or item.get("pd_path"),
                raw=item,
                updated_at=str(data.get("updatedAt") or data.get("updated_at") or now),
            )
        )
    return output


def workflow_views(workflow: Workflow) -> list[JsonDict]:
    return workflow.views


def resolve_project_path(project: Project, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        override = _branch_config_override(project, path)
        if override is not None:
            return override
        resolved = (project.root_path / path).resolve()
    ensure_under_project(project, resolved)
    return resolved


def _branch_config_override(project: Project, path: Path) -> Path | None:
    if project.active_config_dir is None:
        return None
    parts = path.parts
    if len(parts) < 4 or parts[0] != ".solo" or parts[1] != "global":
        return None
    if parts[2] not in {"prompts", "status"}:
        return None
    candidate = (project.active_config_dir / Path(*parts[2:])).resolve()
    if candidate.exists():
        ensure_under_project(project, candidate)
        return candidate
    return None


def ensure_under_project(project: Project, path: Path) -> None:
    try:
        path.resolve().relative_to(project.root_path.resolve())
    except ValueError as exc:
        raise ValidationError(f"path is outside project root: {path}") from exc


def resolve_template(value: str, project: Project, workflow: Workflow, run_id: str | None) -> str:
    scope_path = project.root_path
    replacements = {
        "projectId": project.id,
        "projectRoot": str(project.root_path),
        "runtimeDir": str(project.runtime_dir),
        "scopePath": str(scope_path),
        "workflowId": workflow.id,
        "runId": run_id or "",
        "activeBranch": project.active_branch or "",
        "defaultBranch": project.default_branch,
    }
    for key, replacement in replacements.items():
        value = value.replace("{" + key + "}", replacement)
    return value


def resolve_template_path(
    project: Project, value: str, workflow: Workflow, run_id: str | None
) -> Path:
    return resolve_project_path(project, resolve_template(value, project, workflow, run_id))


def _empty_status() -> JsonDict:
    return {
        "updatedAt": now_iso(),
        "summary": {"total": 0, "running": 0, "completed": 0, "failed": 0, "skipped": 0},
        "items": [],
    }
