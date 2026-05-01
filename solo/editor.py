from __future__ import annotations

import json
import os
import hashlib
import ipaddress
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

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


def editor_id_for(scope_path: Path) -> str:
    digest = hashlib.sha1(str(scope_path.resolve()).encode("utf-8")).hexdigest()
    return f"editor-{digest[:16]}"


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_editor(project: Project, scope_path: Path, public_origin: str | None = None) -> dict:
    scope_path = scope_path.resolve()
    ensure_under_project(project, scope_path)
    editor_id = editor_id_for(scope_path)
    record_path = project.runtime_dir / "editors" / f"{editor_id}.json"
    if record_path.exists():
        data = json.loads(record_path.read_text(encoding="utf-8"))
        if _pid_is_alive(data.get("pid")):
            return editor_response(data, public_origin)
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
        "editorId": editor_id,
        "scopePath": str(scope_path),
        "port": port,
        "pid": process.pid,
        "localUrl": f"http://127.0.0.1:{port}",
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return editor_response(data, public_origin)


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


def editor_response(data: dict, public_origin: str | None = None) -> dict:
    response = dict(data)
    response["url"] = editor_public_url(data, public_origin)
    return response


def editor_public_url(data: dict, public_origin: str | None = None) -> str:
    local_url = str(data.get("localUrl") or f"http://127.0.0.1:{data['port']}")
    if not public_origin:
        return local_url
    parsed = urlsplit(public_origin)
    hostname = parsed.hostname
    if not hostname or is_local_hostname(hostname):
        return local_url
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{data['editorId']}.{hostname}{port}"


def is_local_hostname(hostname: str) -> bool:
    clean = hostname.strip("[]").lower()
    if clean == "localhost":
        return True
    try:
        return ipaddress.ip_address(clean).is_loopback
    except ValueError:
        return False


def editor_record_path(project: Project, editor_id: str) -> Path:
    return project.runtime_dir / "editors" / f"{editor_id}.json"


def load_editor_record(project: Project, editor_id: str) -> dict | None:
    if not editor_id.startswith("editor-"):
        return None
    path = editor_record_path(project, editor_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not _pid_is_alive(data.get("pid")):
        path.unlink(missing_ok=True)
        return None
    port = data.get("port")
    if not isinstance(port, int) or port <= 0:
        return None
    return data


def editor_id_from_host(host: str | None) -> str | None:
    if not host:
        return None
    hostname = host.split(":", 1)[0].lower()
    first_label = hostname.split(".", 1)[0]
    if first_label.startswith("editor-"):
        return first_label
    return None


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
