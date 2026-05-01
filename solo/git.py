from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def is_git_repo(root: Path) -> bool:
    result = run_git(root, "rev-parse", "--show-toplevel")
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == root.resolve()


def active_branch(root: Path) -> str | None:
    result = run_git(root, "branch", "--show-current")
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def default_branch(root: Path) -> str:
    for ref in ("refs/remotes/origin/HEAD", "HEAD"):
        result = run_git(root, "symbolic-ref", "--short", ref)
        if result.returncode == 0:
            value = result.stdout.strip()
            if value.startswith("origin/"):
                value = value.removeprefix("origin/")
            if value:
                return value
    return active_branch(root) or "main"


def dirty_status(root: Path) -> str:
    result = run_git(root, "status", "--short")
    if result.returncode != 0:
        return "unknown"
    return "dirty" if result.stdout.strip() else "clean"


def worktrees(root: Path) -> list[dict[str, str]]:
    result = run_git(root, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        return []
    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line:
            if current:
                rows.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        rows.append(current)
    return rows


def diff(root: Path, cwd: Path, base_ref: str | None = None) -> str:
    args = ["diff"]
    if base_ref:
        args.append(base_ref)
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode not in (0, 1):
        return result.stderr
    return result.stdout


def create_worktree(root: Path, path: Path, branch_name: str, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    result = run_git(root, "worktree", "add", str(path), "-b", branch_name, base_ref)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"failed to create worktree: {path}")
