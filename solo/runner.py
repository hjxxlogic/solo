from __future__ import annotations

import subprocess
import os
import signal
import uuid
from pathlib import Path

from . import git
from .events import EventBus
from .errors import NotFoundError, ValidationError
from .models import JsonDict, Project, Run, Workflow, now_iso
from .store import Store
from .workflow import find_action, resolve_template, resolve_template_path, status_data


class ActionRunner:
    def __init__(self, project: Project, store: Store, events: EventBus | None = None):
        self.project = project
        self.store = store
        self.events = events or EventBus()

    def create_run(
        self,
        workflow: Workflow,
        action_id: str,
        *,
        work_item_id: str | None = None,
        dry_run: bool = False,
        inputs: JsonDict | None = None,
    ) -> Run:
        action = find_action(workflow, action_id)
        runner = str(action.get("runner") or "command")
        if runner not in {"command", "codex"}:
            raise ValidationError(f"unsupported runner for {workflow.id}/{action_id}: {runner}")

        run_id = uuid.uuid4().hex[:12]
        cwd = self._resolve_action_cwd(workflow, action, run_id)
        log_path = self.project.runtime_dir / "logs" / f"{run_id}.log"
        final_path = self.project.runtime_dir / "logs" / f"{run_id}.final.txt"
        prompt_path = (
            self.project.runtime_dir / "prompts" / f"{run_id}.prompt.txt"
            if runner == "codex" or action.get("promptFile") or inputs
            else None
        )
        created = now_iso()
        run = Run(
            id=run_id,
            project_id=self.project.id,
            workflow_id=workflow.id,
            action_id=action_id,
            work_item_id=work_item_id,
            runner=runner,
            status="created",
            scope_type=str(action.get("scopeType") or workflow.scope_type),
            scope_ref=action.get("scopeRef") or self.project.active_branch,
            cwd=cwd,
            prompt_path=prompt_path,
            log_path=log_path,
            final_message_path=final_path if runner == "codex" else None,
            pid=None,
            return_code=None,
            created_at=created,
            updated_at=created,
        )
        if prompt_path is not None:
            prompt = self._build_prompt(workflow, action, run_id, inputs or {})
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")

        if dry_run:
            run.status = "dry_run"
            run.return_code = 0
            run.finished_at = now_iso()
            run.updated_at = run.finished_at
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("dry-run\n", encoding="utf-8")
            if run.final_message_path:
                run.final_message_path.write_text("dry-run\n", encoding="utf-8")
            self.store.save_run(run)
            self.events.publish("run_dry_run", run=run.to_dict())
            return run

        self.store.save_run(run)
        self.events.publish("run_created", run=run.to_dict())
        return run

    def run_sync(
        self,
        workflow: Workflow,
        action_id: str,
        *,
        work_item_id: str | None = None,
        dry_run: bool = False,
        inputs: JsonDict | None = None,
    ) -> Run:
        run = self.create_run(
            workflow,
            action_id,
            work_item_id=work_item_id,
            dry_run=dry_run,
            inputs=inputs,
        )
        if dry_run:
            return run
        action = find_action(workflow, action_id)
        if run.runner == "command":
            self._run_command(run, workflow, action)
        elif run.runner == "codex":
            self._run_codex(run, workflow, action)
        else:
            raise ValidationError(f"unsupported runner: {run.runner}")

        try:
            status = status_data(self.project, workflow)
            self.events.publish("workflow_status_updated", workflowId=workflow.id, status=status)
            from .workflow import work_items

            for item in work_items(self.project, workflow):
                self.events.publish("work_item_updated", workflowId=workflow.id, item=item.to_dict())
        except Exception as exc:  # Keep action result intact even if status refresh fails.
            with run.log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[solo] status refresh failed: {exc}\n")
        return run

    def get_run(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise NotFoundError(f"run not found: {run_id}")
        return run

    def stop_run(self, run_id: str) -> Run:
        run = self.get_run(run_id)
        if run.status != "running" or run.pid is None:
            return run
        try:
            os.killpg(run.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            raise ValidationError(f"cannot stop run {run_id}: {exc}") from exc
        run.status = "stopped"
        run.finished_at = now_iso()
        run.updated_at = run.finished_at
        self.store.save_run(run)
        self.events.publish("run_stopped", run=run.to_dict())
        return run

    def bootstrap_workflow(self, goal: str, *, dry_run: bool = False) -> Run:
        if not goal.strip():
            raise ValidationError("workflow goal is required")
        run_id = uuid.uuid4().hex[:12]
        prompt_path = self.project.runtime_dir / "prompts" / f"{run_id}.prompt.txt"
        log_path = self.project.runtime_dir / "logs" / f"{run_id}.log"
        final_path = self.project.runtime_dir / "logs" / f"{run_id}.final.txt"
        created = now_iso()
        run = Run(
            id=run_id,
            project_id=self.project.id,
            workflow_id="__bootstrap__",
            action_id="bootstrap-workflow",
            work_item_id=None,
            runner="codex",
            status="created",
            scope_type="global",
            scope_ref=self.project.active_branch,
            cwd=self.project.root_path,
            prompt_path=prompt_path,
            log_path=log_path,
            final_message_path=final_path,
            pid=None,
            return_code=None,
            created_at=created,
            updated_at=created,
        )
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(_bootstrap_prompt(goal), encoding="utf-8")
        if dry_run:
            run.status = "dry_run"
            run.return_code = 0
            run.finished_at = now_iso()
            run.updated_at = run.finished_at
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("dry-run\n", encoding="utf-8")
            final_path.write_text("dry-run\n", encoding="utf-8")
            self.store.save_run(run)
            self.events.publish("run_dry_run", run=run.to_dict())
            return run
        self.store.save_run(run)
        self._run_codex(run, _bootstrap_workflow_model(self.project.id), {})
        return run

    def _run_command(self, run: Run, workflow: Workflow, action: JsonDict) -> None:
        command = action.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValidationError(f"command action must declare a string list: {workflow.id}/{run.action_id}")
        command = [resolve_template(part, self.project, workflow, run.id) for part in command]
        self._run_process(run, command, stdin=None)

    def _run_codex(self, run: Run, workflow: Workflow, action: JsonDict) -> None:
        codex_bin = str(action.get("codexBin") or "codex")
        command = [codex_bin, "exec", "-C", str(run.cwd)]
        if run.final_message_path is not None:
            command.extend(["-o", str(run.final_message_path)])
        command.append("-")
        prompt = run.prompt_path.read_text(encoding="utf-8") if run.prompt_path else ""
        self._run_process(run, command, stdin=prompt)

    def _run_process(self, run: Run, command: list[str], stdin: str | None) -> None:
        run.status = "running"
        run.started_at = now_iso()
        run.updated_at = run.started_at
        self.store.save_run(run)
        self.events.publish("run_started", run=run.to_dict(), command=command)

        run.log_path.parent.mkdir(parents=True, exist_ok=True)
        with run.log_path.open("w", encoding="utf-8") as log:
            log.write(f"$ {' '.join(command)}\n\n")
            process = subprocess.Popen(
                command,
                cwd=run.cwd,
                text=True,
                stdin=subprocess.PIPE if stdin is not None else None,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            run.pid = process.pid
            self.store.save_run(run)
            process.communicate(stdin)
            run.return_code = process.returncode

        latest = self.store.get_run(run.id)
        if latest is not None and latest.status == "stopped":
            run.status = "stopped"
            run.return_code = run.return_code
            run.finished_at = latest.finished_at or now_iso()
            run.updated_at = run.finished_at
            self.store.save_run(run)
            return
        if run.return_code is not None and run.return_code < 0:
            run.status = "stopped"
            run.finished_at = now_iso()
            run.updated_at = run.finished_at
            self.store.save_run(run)
            self.events.publish("run_stopped", run=run.to_dict())
            return

        run.status = "completed" if run.return_code == 0 else "failed"
        run.finished_at = now_iso()
        run.updated_at = run.finished_at
        self.store.save_run(run)
        if run.log_path.exists():
            self.events.publish("run_log", runId=run.id, text=run.log_path.read_text(encoding="utf-8"))
        self.events.publish("run_completed" if run.status == "completed" else "run_failed", run=run.to_dict())

    def _resolve_action_cwd(self, workflow: Workflow, action: JsonDict, run_id: str) -> Path:
        worktree = action.get("worktree")
        if isinstance(worktree, dict):
            mode = str(worktree.get("mode") or "none")
            if mode == "create":
                path = resolve_template_path(
                    self.project,
                    str(worktree.get("path") or ".solo-runtime/worktrees/{runId}"),
                    workflow,
                    run_id,
                )
                branch_name = resolve_template(
                    str(worktree.get("branchName") or "solo/{runId}"),
                    self.project,
                    workflow,
                    run_id,
                )
                base_ref = resolve_template(
                    str(worktree.get("baseRef") or self.project.default_branch),
                    self.project,
                    workflow,
                    run_id,
                )
                try:
                    git.create_worktree(self.project.root_path, path, branch_name, base_ref)
                except RuntimeError as exc:
                    raise ValidationError(str(exc)) from exc
                return path
            if mode == "existing":
                return resolve_template_path(
                    self.project,
                    str(worktree.get("path") or action.get("cwd") or "{projectRoot}"),
                    workflow,
                    run_id,
                )
            if mode != "none":
                raise ValidationError(f"unsupported worktree mode: {mode}")
        return resolve_template_path(
            self.project, str(action.get("cwd") or "{projectRoot}"), workflow, run_id
        )

    def _build_prompt(
        self, workflow: Workflow, action: JsonDict, run_id: str, inputs: JsonDict
    ) -> str:
        prompt_file = action.get("promptFile")
        if prompt_file:
            path = resolve_template_path(self.project, str(prompt_file), workflow, run_id)
            if path.exists():
                prompt = path.read_text(encoding="utf-8")
            else:
                prompt = ""
        else:
            prompt = str(action.get("prompt") or "")
        prompt = resolve_template(prompt, self.project, workflow, run_id)
        if inputs:
            prompt += "\n\nInputs:\n"
            for key, value in sorted(inputs.items()):
                prompt += f"- {key}: {value}\n"
        return prompt


def _bootstrap_prompt(goal: str) -> str:
    return f"""你正在为当前项目创建 SOLO workflow。

目标：
{goal}

要求：
- 默认工作流定义写入 .solo/global/workflows/{{workflowId}}.yaml
- 如果用户要求 branch/worktree 特定流程，写入 .solo/<git branch>/workflows/{{workflowId}}.yaml
- 状态查询必须输出 JSON
- 支持 dry-run、run-one、status-all、resume
- 日志和最终结果路径应可被 SOLO UI 展示
- 不要修改与该 workflow 无关的项目文件
- SOLO 是显示层与执行层，不要把业务策略写入 SOLO 本身

完成后总结创建或修改的文件、验证方式和遗留问题。
"""


def _bootstrap_workflow_model(project_id: str) -> Workflow:
    return Workflow(
        id="__bootstrap__",
        project_id=project_id,
        title="Bootstrap Workflow",
        description="Create or update a project-owned SOLO workflow.",
        definition_path=Path("."),
        scope_type="global",
        status={},
        actions=[],
        views=[],
    )
