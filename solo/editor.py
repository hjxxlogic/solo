from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

from .errors import ValidationError
from .models import Project
from .workflow import ensure_under_project


CODE_SERVER_ENV_REMOVE = (
    "VSCODE_IPC_HOOK_CLI",
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
)


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_editor(project: Project, scope_path: Path) -> dict:
    scope_path = scope_path.resolve()
    ensure_under_project(project, scope_path)
    editor_id = str(scope_path).replace("/", "_").replace("\\", "_").strip("_")
    record_path = project.runtime_dir / "editors" / f"{editor_id}.json"
    if record_path.exists():
        data = json.loads(record_path.read_text(encoding="utf-8"))
        if _pid_is_alive(data.get("pid")):
            return data
        record_path.unlink(missing_ok=True)

    port = allocate_port()
    code_server = find_code_server(project)
    if not code_server:
        raise ValidationError("code-server executable was not found")
    command = [
        code_server,
        "--bind-addr",
        f"127.0.0.1:{port}",
        "--auth",
        "none",
        str(scope_path),
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=scope_path,
            env=code_server_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise ValidationError("code-server executable was not found") from exc

    data = {
        "scopePath": str(scope_path),
        "port": port,
        "pid": process.pid,
        "url": f"http://127.0.0.1:{port}",
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def _pid_is_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def code_server_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in CODE_SERVER_ENV_REMOVE:
        env.pop(name, None)
    return env


def find_code_server(project: Project) -> str | None:
    global_bin = shutil.which("code-server")
    if global_bin:
        return global_bin
    repo_local = project.root_path / ".tools" / "code-server" / "node_modules" / ".bin" / "code-server"
    if repo_local.exists():
        return str(repo_local)
    package_local = Path(__file__).resolve().parents[1] / ".tools" / "code-server" / "node_modules" / ".bin" / "code-server"
    if package_local.exists():
        return str(package_local)
    return None
