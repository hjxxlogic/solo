from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .project import git_info
from .workflow import load_workflows


STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def index_context(ctx: Any) -> dict:
    project = ctx.project.to_dict()
    workflows = [workflow.to_dict() for workflow in load_workflows(ctx.project)]
    runs = ctx.store.list_runs(ctx.project.id)
    codex_sessions = ctx.store.list_codex_sessions(ctx.project.id)
    git = git_info(ctx.project)
    return {
        "app_name": "SOLO",
        "version": __version__,
        "project": project,
        "git": git,
        "workflows": workflows,
        "runs": runs,
        "codex_sessions": codex_sessions,
        "bootstrap": {
            "version": __version__,
            "project": project,
            "git": git,
            "workflows": workflows,
            "runs": runs,
            "codexSessions": codex_sessions,
        },
    }


def render_index(ctx: Any) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Jinja2 is required to render the SOLO UI") from exc

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["url_for"] = _url_for
    return env.get_template("index.html").render(**index_context(ctx))


def _url_for(name: str, **params: str) -> str:
    if name == "static":
        path = params.get("path", "")
        return f"/static/{path.lstrip('/')}"
    return "#"
