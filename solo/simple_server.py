from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .app import SoloContext
from .editor import open_editor
from .errors import NotFoundError, SoloError
from .git import diff as git_diff
from .init import install_codex_hooks
from .project import git_info
from .ui import STATIC_DIR, render_index
from .workflow import find_workflow, load_workflows, status_data, workflow_views, work_items


def serve(root: Path, host: str, port: int) -> None:
    ctx = SoloContext(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle(self, method: str) -> None:
            try:
                path = urlparse(self.path).path
                if method == "GET" and self._serve_static(path):
                    return
                body = self._read_json() if method == "POST" else {}
                result = route(ctx, method, path, body)
                if isinstance(result, str):
                    self._send_text(result)
                else:
                    self._send_json(result)
            except NotFoundError as exc:
                self._send_json({"detail": str(exc)}, HTTPStatus.NOT_FOUND)
            except SoloError as exc:
                self._send_json({"detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _read_json(self) -> dict:
            length = int(self.headers.get("content-length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw or "{}")

        def _send_json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _send_text(self, data: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            raw = data.encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "text/plain; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _serve_static(self, path: str) -> bool:
            if path == "/":
                self._send_html(render_index(ctx))
                return True
            elif path.startswith("/static/"):
                relative = Path(path.removeprefix("/static/"))
                file_path = (STATIC_DIR / relative).resolve()
                try:
                    file_path.relative_to(STATIC_DIR.resolve())
                except ValueError:
                    self._send_json({"detail": "invalid static path"}, HTTPStatus.BAD_REQUEST)
                    return True
            else:
                return False
            if not file_path.exists() or not file_path.is_file():
                self._send_json({"detail": "static file not found"}, HTTPStatus.NOT_FOUND)
                return True
            raw = file_path.read_bytes()
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return True

        def _send_html(self, data: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            raw = data.encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SOLO listening on http://{host}:{port}")
    server.serve_forever()


def route(ctx: SoloContext, method: str, path: str, body: dict) -> object:
    parts = [part for part in path.split("/") if part]
    if path == "/":
        return {"name": "SOLO", "project": ctx.project.to_dict()}
    if parts == ["api", "events"]:
        return "SSE requires the FastAPI server; install project dependencies for /api/events.\n"
    if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "git":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return git_info(project)
    if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "codex-sessions":
        project, store, _runner = _project_scope(ctx, parts[2])
        return store.list_codex_sessions(project.id)
    if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "init":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return install_codex_hooks(project)
    if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "open-editor":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return open_editor(project, project.root_path)
    if len(parts) == 3 and parts[:2] == ["api", "projects"]:
        return ctx.get_project(parts[2]).to_dict()
    if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "refresh":
        project, store, _runner = _project_scope(ctx, parts[2])
        return {
            "project": project.to_dict(),
            "workflows": _workflow_dicts(project),
            "runs": store.list_runs(project.id),
        }
    if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "workflows":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return _workflow_dicts(project)
    if (
        method == "POST"
        and len(parts) == 5
        and parts[:2] == ["api", "projects"]
        and parts[3:] == ["workflows", "bootstrap"]
    ):
        _project, _store, runner = _project_scope(ctx, parts[2])
        return runner.bootstrap_workflow(
            str(body.get("goal") or ""),
            dry_run=bool(body.get("dryRun", False)),
        ).to_dict()
    if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "workflows":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return find_workflow(project, parts[4]).to_dict()
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "workflows" and parts[5] == "status":
        project, _store, _runner = _project_scope(ctx, parts[2])
        workflow = find_workflow(project, parts[4])
        return status_data(project, workflow)
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "workflows" and parts[5] == "items":
        project, _store, _runner = _project_scope(ctx, parts[2])
        workflow = find_workflow(project, parts[4])
        return [item.to_dict() for item in work_items(project, workflow)]
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "workflows" and parts[5] == "views":
        project, _store, _runner = _project_scope(ctx, parts[2])
        return workflow_views(find_workflow(project, parts[4]))
    if (
        method == "POST"
        and len(parts) == 8
        and parts[:2] == ["api", "projects"]
        and parts[3] == "workflows"
        and parts[5] == "actions"
        and parts[7] == "run"
    ):
        project, _store, runner = _project_scope(ctx, parts[2])
        workflow = find_workflow(project, parts[4])
        run = runner.run_sync(
            workflow,
            parts[6],
            work_item_id=body.get("workItemId"),
            dry_run=bool(body.get("dryRun", False)),
            inputs=body.get("inputs") if isinstance(body.get("inputs"), dict) else None,
        )
        return run.to_dict()
    if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "runs":
        project, store, _runner = _project_scope(ctx, parts[2])
        return store.list_runs(project.id)
    if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "runs":
        _project, _store, runner = _project_scope(ctx, parts[2])
        return runner.get_run(parts[4]).to_dict()
    if method == "POST" and len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "stop":
        _project, _store, runner = _project_scope(ctx, parts[2])
        return runner.stop_run(parts[4]).to_dict()
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "logs":
        _project, _store, runner = _project_scope(ctx, parts[2])
        run = runner.get_run(parts[4])
        return run.log_path.read_text(encoding="utf-8") if run.log_path.exists() else ""
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "prompt":
        _project, _store, runner = _project_scope(ctx, parts[2])
        run = runner.get_run(parts[4])
        path = run.prompt_path
        return path.read_text(encoding="utf-8") if path and path.exists() else ""
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "final":
        _project, _store, runner = _project_scope(ctx, parts[2])
        run = runner.get_run(parts[4])
        path = run.final_message_path
        return path.read_text(encoding="utf-8") if path and path.exists() else ""
    if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "diff":
        project, _store, runner = _project_scope(ctx, parts[2])
        run = runner.get_run(parts[4])
        return git_diff(project.root_path, run.cwd, project.default_branch)
    if method == "POST" and len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "runs" and parts[5] == "open-editor":
        project, _store, runner = _project_scope(ctx, parts[2])
        run = runner.get_run(parts[4])
        return open_editor(project, run.cwd)
    if len(parts) == 3 and parts[:2] == ["api", "workflows"]:
        return find_workflow(ctx.project, parts[2]).to_dict()
    if len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "status":
        workflow = find_workflow(ctx.project, parts[2])
        return status_data(ctx.project, workflow)
    if len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "items":
        workflow = find_workflow(ctx.project, parts[2])
        return [item.to_dict() for item in work_items(ctx.project, workflow)]
    if len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "views":
        return workflow_views(find_workflow(ctx.project, parts[2]))
    if (
        method == "POST"
        and len(parts) == 6
        and parts[:2] == ["api", "workflows"]
        and parts[3] == "actions"
        and parts[5] == "run"
    ):
        workflow = find_workflow(ctx.project, parts[2])
        run = ctx.runner.run_sync(
            workflow,
            parts[4],
            work_item_id=body.get("workItemId"),
            dry_run=bool(body.get("dryRun", False)),
            inputs=body.get("inputs") if isinstance(body.get("inputs"), dict) else None,
        )
        return run.to_dict()
    if len(parts) == 3 and parts[:2] == ["api", "runs"]:
        return ctx.runner.get_run(parts[2]).to_dict()
    if len(parts) == 2 and parts == ["api", "runs"]:
        return ctx.store.list_runs(ctx.project.id)
    if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "stop":
        return ctx.runner.stop_run(parts[2]).to_dict()
    if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "logs":
        run = ctx.runner.get_run(parts[2])
        return run.log_path.read_text(encoding="utf-8") if run.log_path.exists() else ""
    if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "prompt":
        run = ctx.runner.get_run(parts[2])
        path = run.prompt_path
        return path.read_text(encoding="utf-8") if path and path.exists() else ""
    if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "final":
        run = ctx.runner.get_run(parts[2])
        path = run.final_message_path
        return path.read_text(encoding="utf-8") if path and path.exists() else ""
    if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "diff":
        run = ctx.runner.get_run(parts[2])
        return git_diff(ctx.project.root_path, run.cwd, ctx.project.default_branch)
    if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "open-editor":
        run = ctx.runner.get_run(parts[2])
        return open_editor(ctx.project, run.cwd)
    raise NotFoundError(f"route not found: {method} {path}")


def _project_scope(ctx: SoloContext, project_id: str):
    project = ctx.get_project(project_id)
    return project, ctx.get_store(project_id), ctx.get_runner(project_id)


def _workflow_dicts(project) -> list[dict]:
    return [workflow.to_dict() for workflow in load_workflows(project)]
