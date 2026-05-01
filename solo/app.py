import asyncio
from pathlib import Path
from typing import Any

from . import __version__
from .editor import open_editor
from .errors import NotFoundError, SoloError
from .events import EventBus, format_sse
from .git import diff as git_diff
from .project import ensure_project, git_info
from .proxy import EditorProxyMiddleware, request_public_origin
from .runner import ActionRunner
from .store import Store
from .ui import STATIC_DIR, TEMPLATE_DIR, index_context
from .workflow import find_workflow, load_workflows, status_data, workflow_views, work_items


class SoloContext:
    def __init__(self, root: Path):
        self.events = EventBus()
        self.open_project(root)

    def open_project(self, root: Path) -> None:
        self.project = ensure_project(root)
        self.store = Store(self.project.runtime_dir / "db.sqlite")
        self.runner = ActionRunner(self.project, self.store, self.events)


def create_app(root: Path):
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import PlainTextResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ImportError as exc:  # pragma: no cover - exercised only in missing dependency environments.
        raise RuntimeError("serve requires fastapi and uvicorn to be installed") from exc

    ctx = SoloContext(root)
    app = FastAPI(title="SOLO", version=__version__)
    app.add_middleware(EditorProxyMiddleware, project_getter=lambda: ctx.project)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def handle_error(exc: Exception) -> HTTPException:
        status = 404 if isinstance(exc, NotFoundError) else 400
        return HTTPException(status_code=status, detail=str(exc))

    @app.post("/api/projects/open")
    def open_project(body: dict[str, Any] | None = None):
        try:
            requested = Path(str((body or {}).get("path") or ctx.project.root_path)).resolve()
            ctx.open_project(requested)
            ctx.events.publish("project_loaded", project=ctx.project.to_dict())
            return ctx.project.to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        return ctx.project.to_dict()

    @app.post("/api/projects/{project_id}/refresh")
    def refresh_project(project_id: str):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        workflows = [workflow.to_dict() for workflow in load_workflows(ctx.project)]
        ctx.events.publish("project_loaded", project=ctx.project.to_dict())
        for workflow in workflows:
            ctx.events.publish("workflow_loaded", workflow=workflow)
        return {"project": ctx.project.to_dict(), "workflows": workflows}

    @app.get("/api/projects/{project_id}/git")
    def get_git(project_id: str):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        return git_info(ctx.project)

    @app.post("/api/projects/{project_id}/open-editor")
    def project_open_editor(project_id: str, request: Request):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        try:
            data = open_editor(ctx.project, ctx.project.root_path, request_public_origin(request))
            ctx.events.publish("editor_started", projectId=project_id, editor=data)
            return data
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/projects/{project_id}/workflows")
    def get_workflows(project_id: str):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        return [workflow.to_dict() for workflow in load_workflows(ctx.project)]

    @app.post("/api/projects/{project_id}/workflows/bootstrap")
    def bootstrap_workflow(project_id: str, body: dict[str, Any] | None = None):
        if project_id != ctx.project.id:
            raise HTTPException(status_code=404, detail="project not found")
        body = body or {}
        try:
            return ctx.runner.bootstrap_workflow(
                str(body.get("goal") or ""),
                dry_run=bool(body.get("dryRun", False)),
            ).to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        try:
            return find_workflow(ctx.project, workflow_id).to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.post("/api/workflows/{workflow_id}/status")
    def get_status(workflow_id: str):
        try:
            workflow = find_workflow(ctx.project, workflow_id)
            data = status_data(ctx.project, workflow)
            ctx.events.publish("workflow_status_updated", workflowId=workflow_id, status=data)
            for item in work_items(ctx.project, workflow):
                ctx.events.publish("work_item_updated", workflowId=workflow_id, item=item.to_dict())
            return data
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/workflows/{workflow_id}/items")
    def get_items(workflow_id: str):
        try:
            workflow = find_workflow(ctx.project, workflow_id)
            return [item.to_dict() for item in work_items(ctx.project, workflow)]
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/workflows/{workflow_id}/views")
    def get_views(workflow_id: str):
        try:
            return workflow_views(find_workflow(ctx.project, workflow_id))
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.post("/api/workflows/{workflow_id}/actions/{action_id}/run")
    def run_action(workflow_id: str, action_id: str, body: dict[str, Any] | None = None):
        body = body or {}
        try:
            workflow = find_workflow(ctx.project, workflow_id)
            run = ctx.runner.run_sync(
                workflow,
                action_id,
                work_item_id=body.get("workItemId"),
                dry_run=bool(body.get("dryRun", False)),
                inputs=body.get("inputs") if isinstance(body.get("inputs"), dict) else None,
            )
            return run.to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @get_run_route(app, "/api/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return ctx.runner.get_run(run_id).to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/runs")
    def get_runs():
        return ctx.store.list_runs(ctx.project.id)

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str):
        try:
            return ctx.runner.stop_run(run_id).to_dict()
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/runs/{run_id}/logs", response_class=PlainTextResponse)
    def get_run_logs(run_id: str):
        try:
            run = ctx.runner.get_run(run_id)
            return run.log_path.read_text(encoding="utf-8") if run.log_path.exists() else ""
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/runs/{run_id}/prompt", response_class=PlainTextResponse)
    def get_run_prompt(run_id: str):
        try:
            run = ctx.runner.get_run(run_id)
            path = run.prompt_path
            return path.read_text(encoding="utf-8") if path and path.exists() else ""
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/runs/{run_id}/final", response_class=PlainTextResponse)
    def get_run_final(run_id: str):
        try:
            run = ctx.runner.get_run(run_id)
            path = run.final_message_path
            return path.read_text(encoding="utf-8") if path and path.exists() else ""
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/runs/{run_id}/diff", response_class=PlainTextResponse)
    def get_run_diff(run_id: str):
        try:
            run = ctx.runner.get_run(run_id)
            return git_diff(ctx.project.root_path, run.cwd, ctx.project.default_branch)
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.post("/api/runs/{run_id}/open-editor")
    def run_open_editor(run_id: str, request: Request):
        try:
            run = ctx.runner.get_run(run_id)
            data = open_editor(ctx.project, run.cwd, request_public_origin(request))
            ctx.events.publish("editor_started", runId=run_id, editor=data)
            return data
        except SoloError as exc:
            raise handle_error(exc) from exc

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            queue = ctx.events.subscribe_queue()
            try:
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    yield format_sse(event)
            finally:
                ctx.events.unsubscribe_queue(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            index_context(ctx),
        )

    return app


def get_run_route(app, path: str):
    # Keeps the decorated function visually grouped with other run endpoints.
    return app.get(path)
