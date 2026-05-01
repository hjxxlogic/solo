from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    root_path: Path
    default_branch: str
    active_branch: str | None
    global_config_dir: Path
    active_config_dir: Path | None
    effective_workflow_dirs: tuple[Path, ...]
    runtime_dir: Path

    def to_dict(self) -> JsonDict:
        timestamp = now_iso()
        return {
            "id": self.id,
            "name": self.name,
            "rootPath": str(self.root_path),
            "defaultBranch": self.default_branch,
            "activeBranch": self.active_branch,
            "globalConfigDir": str(self.global_config_dir.relative_to(self.root_path)),
            "activeConfigDir": (
                str(self.active_config_dir.relative_to(self.root_path))
                if self.active_config_dir is not None
                else None
            ),
            "effectiveWorkflowDirs": [
                str(path.relative_to(self.root_path)) for path in self.effective_workflow_dirs
            ],
            "runtimeDir": str(self.runtime_dir.relative_to(self.root_path)),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }


@dataclass(frozen=True)
class Workflow:
    id: str
    project_id: str
    title: str
    description: str
    definition_path: Path
    scope_type: str
    status: JsonDict
    actions: list[JsonDict] = field(default_factory=list)
    views: list[JsonDict] = field(default_factory=list)
    raw: JsonDict = field(default_factory=dict)
    last_status_at: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "title": self.title,
            "description": self.description,
            "definitionPath": str(self.definition_path),
            "scopeType": self.scope_type,
            "status": self.status,
            "actions": self.actions,
            "views": self.views,
            "lastStatusAt": self.last_status_at,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class WorkItem:
    id: str
    workflow_id: str
    external_id: str
    title: str
    status: str
    scope_type: str
    scope_ref: str | None
    source_path: str | None
    raw: JsonDict
    updated_at: str

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "workflowId": self.workflow_id,
            "externalId": self.external_id,
            "title": self.title,
            "status": self.status,
            "scopeType": self.scope_type,
            "scopeRef": self.scope_ref,
            "sourcePath": self.source_path,
            "raw": self.raw,
            "updatedAt": self.updated_at,
        }


@dataclass
class Run:
    id: str
    project_id: str
    workflow_id: str
    action_id: str
    work_item_id: str | None
    runner: str
    status: str
    scope_type: str
    scope_ref: str | None
    cwd: Path
    prompt_path: Path | None
    log_path: Path
    final_message_path: Path | None
    pid: int | None
    return_code: int | None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "workflowId": self.workflow_id,
            "actionId": self.action_id,
            "workItemId": self.work_item_id,
            "runner": self.runner,
            "status": self.status,
            "scopeType": self.scope_type,
            "scopeRef": self.scope_ref,
            "cwd": str(self.cwd),
            "promptPath": str(self.prompt_path) if self.prompt_path else None,
            "logPath": str(self.log_path),
            "finalMessagePath": str(self.final_message_path) if self.final_message_path else None,
            "pid": self.pid,
            "returnCode": self.return_code,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "updatedAt": self.updated_at or self.created_at,
        }

    @classmethod
    def from_dict(cls, data: JsonDict) -> "Run":
        return cls(
            id=str(data["id"]),
            project_id=str(data["projectId"]),
            workflow_id=str(data["workflowId"]),
            action_id=str(data["actionId"]),
            work_item_id=data.get("workItemId"),
            runner=str(data["runner"]),
            status=str(data["status"]),
            scope_type=str(data["scopeType"]),
            scope_ref=data.get("scopeRef"),
            cwd=Path(str(data["cwd"])),
            prompt_path=Path(str(data["promptPath"])) if data.get("promptPath") else None,
            log_path=Path(str(data["logPath"])),
            final_message_path=(
                Path(str(data["finalMessagePath"])) if data.get("finalMessagePath") else None
            ),
            pid=data.get("pid"),
            return_code=data.get("returnCode"),
            created_at=str(data["createdAt"]),
            started_at=data.get("startedAt"),
            finished_at=data.get("finishedAt"),
            updated_at=data.get("updatedAt"),
        )
