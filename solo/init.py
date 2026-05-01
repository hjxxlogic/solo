from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from .models import Project


HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "Stop")


def install_codex_hooks(project: Project) -> dict:
    codex_dir = project.root_path / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    config_path = codex_dir / "config.toml"
    hooks_path = codex_dir / "hooks.json"

    _enable_codex_hooks(config_path)
    _write_hooks(hooks_path, project.root_path)
    return {
        "configPath": str(config_path),
        "hooksPath": str(hooks_path),
        "events": list(HOOK_EVENTS),
    }


def _enable_codex_hooks(path: Path) -> None:
    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        content = ""

    lines = content.splitlines()
    feature_index = _section_index(lines, "features")
    if feature_index is None:
        suffix = "\n" if content and not content.endswith("\n") else ""
        path.write_text(f"{content}{suffix}[features]\ncodex_hooks = true\n", encoding="utf-8")
        return

    end = _section_end(lines, feature_index)
    for index in range(feature_index + 1, end):
        if lines[index].strip().startswith("codex_hooks"):
            lines[index] = "codex_hooks = true"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    lines.insert(feature_index + 1, "codex_hooks = true")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _section_index(lines: list[str], section: str) -> int | None:
    header = f"[{section}]"
    for index, line in enumerate(lines):
        if line.strip() == header:
            return index
    return None


def _section_end(lines: list[str], section_index: int) -> int:
    for index in range(section_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return index
    return len(lines)


def _write_hooks(path: Path, repo: Path) -> None:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}

    hooks_data = data.get("hooks")
    if not isinstance(hooks_data, dict):
        hooks_data = {}
    for event in HOOK_EVENTS:
        legacy_groups = data.pop(event, None)
        if event not in hooks_data and isinstance(legacy_groups, list):
            hooks_data[event] = legacy_groups

    for event in HOOK_EVENTS:
        existing = hooks_data.get(event)
        groups = existing if isinstance(existing, list) else []
        groups = [group for group in groups if not _is_solo_hook_group(group)]
        groups.append(_hook_group(event, repo))
        hooks_data[event] = groups
    data["hooks"] = hooks_data

    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hook_group(event: str, repo: Path) -> dict:
    command = (
        f"{shlex.quote(sys.executable)} -m solo.codex_hook "
        f"--event {shlex.quote(event)} "
        f"--repo {shlex.quote(str(repo))}"
    )
    return {
        "hooks": [
            {
                "type": "command",
                "command": command,
            }
        ],
    }


def _is_solo_hook_group(group: object) -> bool:
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if isinstance(hook, dict) and "solo.codex_hook" in str(hook.get("command") or ""):
            return True
    return False
