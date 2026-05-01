from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .app import SoloContext, create_app
from .errors import SoloError
from .models import JsonDict
from .workflow import find_workflow, load_workflows, status_data


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        from .simple_server import serve

        serve(Path(args.repo), args.host, args.port)
        return 0
    try:
        app = create_app(Path(args.repo))
    except RuntimeError:
        from .simple_server import serve

        serve(Path(args.repo), args.host, args.port)
        return 0
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def cmd_workflow_list(args: argparse.Namespace) -> int:
    ctx = SoloContext(Path(args.repo))
    print_json([workflow.to_dict() for workflow in load_workflows(ctx.project)])
    return 0


def cmd_workflow_status(args: argparse.Namespace) -> int:
    ctx = SoloContext(Path(args.repo))
    workflow = find_workflow(ctx.project, args.workflow_id)
    print_json(status_data(ctx.project, workflow))
    return 0


def cmd_workflow_bootstrap(args: argparse.Namespace) -> int:
    ctx = SoloContext(Path(args.repo))
    run = ctx.runner.bootstrap_workflow(args.goal, dry_run=args.dry_run)
    print_json(run.to_dict())
    return 0 if run.status in {"completed", "dry_run"} else 1


def cmd_action_run(args: argparse.Namespace) -> int:
    ctx = SoloContext(Path(args.repo))
    workflow = find_workflow(ctx.project, args.workflow_id)
    inputs: JsonDict = {}
    for raw in args.input or []:
        key, sep, value = raw.partition("=")
        if not sep:
            raise SoloError(f"input must be KEY=VALUE: {raw}")
        inputs[key] = value
    run = ctx.runner.run_sync(
        workflow,
        args.action_id,
        dry_run=args.dry_run,
        work_item_id=args.work_item_id,
        inputs=inputs or None,
    )
    print_json(run.to_dict())
    return 0 if run.status in {"completed", "dry_run"} else 1


def cmd_run_logs(args: argparse.Namespace) -> int:
    ctx = SoloContext(Path(args.repo))
    run = ctx.runner.get_run(args.run_id)
    if run.log_path.exists():
        print(run.log_path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_run_diff(args: argparse.Namespace) -> int:
    from .git import diff as git_diff

    ctx = SoloContext(Path(args.repo))
    run = ctx.runner.get_run(args.run_id)
    print(git_diff(ctx.project.root_path, run.cwd, ctx.project.default_branch), end="")
    return 0


def cmd_run_open_editor(args: argparse.Namespace) -> int:
    from .editor import open_editor

    ctx = SoloContext(Path(args.repo))
    run = ctx.runner.get_run(args.run_id)
    print_json(open_editor(ctx.project, run.cwd))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solo")
    parser.add_argument("--repo", default=".", help="Managed project root. Defaults to current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the SOLO API server.")
    serve.add_argument("repo", nargs="?", default=None, help="Managed project root.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=lambda args: cmd_serve(_fix_repo(args)))

    workflow = subparsers.add_parser("workflow", help="Workflow commands.")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)

    workflow_list = workflow_sub.add_parser("list", help="List workflows.")
    workflow_list.set_defaults(func=cmd_workflow_list)

    workflow_status = workflow_sub.add_parser("status", help="Query workflow status.")
    workflow_status.add_argument("workflow_id")
    workflow_status.set_defaults(func=cmd_workflow_status)

    workflow_bootstrap = workflow_sub.add_parser("bootstrap", help="Create or update a workflow with Codex.")
    workflow_bootstrap.add_argument("--goal", required=True)
    workflow_bootstrap.add_argument("--dry-run", action="store_true")
    workflow_bootstrap.set_defaults(func=cmd_workflow_bootstrap)

    action = subparsers.add_parser("action", help="Action commands.")
    action_sub = action.add_subparsers(dest="action_command", required=True)
    action_run = action_sub.add_parser("run", help="Run a workflow action.")
    action_run.add_argument("workflow_id")
    action_run.add_argument("action_id")
    action_run.add_argument("--dry-run", action="store_true")
    action_run.add_argument("--work-item-id")
    action_run.add_argument("--input", action="append", help="Input as KEY=VALUE. Can be repeated.")
    action_run.set_defaults(func=cmd_action_run)

    run = subparsers.add_parser("run", help="Run inspection commands.")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_logs = run_sub.add_parser("logs", help="Print run logs.")
    run_logs.add_argument("run_id")
    run_logs.set_defaults(func=cmd_run_logs)
    run_diff = run_sub.add_parser("diff", help="Print run git diff.")
    run_diff.add_argument("run_id")
    run_diff.set_defaults(func=cmd_run_diff)
    run_editor = run_sub.add_parser("open-editor", help="Open code-server for a run.")
    run_editor.add_argument("run_id")
    run_editor.set_defaults(func=cmd_run_open_editor)

    return parser


def _fix_repo(args: argparse.Namespace) -> argparse.Namespace:
    if args.repo is None:
        args.repo = "."
    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SoloError as exc:
        print(f"solo: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
