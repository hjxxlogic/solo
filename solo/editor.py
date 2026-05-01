from __future__ import annotations

import json
import os
import hashlib
import ipaddress
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ValidationError
from .models import Project
from .workflow import ensure_under_project


CODE_SERVER_ENV_REMOVE = (
    "CODE_SERVER_PARENT_PID",
    "CODE_SERVER_SESSION_SOCKET",
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
)
CODE_SERVER_ENV_REMOVE_PREFIXES = (
    "ELECTRON_",
    "VSCODE_",
)
CODE_SERVER_PATH_EXCLUDE_PARTS = (
    "/.cursor-server/",
    "/.vscode-server/",
    "/.vscode-remote/",
    "/.windsurf-server/",
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
        if _record_matches_scope(data, scope_path) and _editor_record_is_alive(data):
            return editor_response(data, public_origin)
        record_path.unlink(missing_ok=True)

    port = allocate_port()
    code_server = find_code_server(project)
    if not code_server:
        raise ValidationError("code-server executable was not found")
    editor_runtime_dir = project.runtime_dir / "editors" / editor_id
    user_data_dir = editor_runtime_dir / "user-data"
    extensions_dir = editor_runtime_dir / "extensions"
    log_path = editor_runtime_dir / "code-server.log"
    config_path = editor_runtime_dir / "config.yaml"
    session_socket = Path(tempfile.gettempdir()) / f"solo-{editor_id}.sock"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    extensions_dir.mkdir(parents=True, exist_ok=True)
    session_socket.unlink(missing_ok=True)
    config_path.write_text(
        "\n".join(
            [
                f"bind-addr: 127.0.0.1:{port}",
                "auth: none",
                "cert: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    command = [
        code_server,
        "--config",
        str(config_path),
        "--bind-addr",
        f"127.0.0.1:{port}",
        "--auth",
        "none",
        "--verbose",
        "--ignore-last-opened",
        "--user-data-dir",
        str(user_data_dir),
        "--extensions-dir",
        str(extensions_dir),
        "--session-socket",
        str(session_socket),
        str(scope_path),
    ]
    try:
        log_file = log_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=scope_path,
                env=code_server_env(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_file.close()
    except FileNotFoundError as exc:
        raise ValidationError("code-server executable was not found") from exc
    if not _wait_for_editor_start(port, process):
        output = _read_log_tail(log_path)
        raise ValidationError(f"code-server failed to start for {scope_path}: {output}")

    data = {
        "editorId": editor_id,
        "scopePath": str(scope_path),
        "port": port,
        "pid": process.pid,
        "localUrl": f"http://127.0.0.1:{port}",
        "logPath": str(log_path),
        "userDataDir": str(user_data_dir),
        "extensionsDir": str(extensions_dir),
        "configPath": str(config_path),
        "sessionSocket": str(session_socket),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return editor_response(data, public_origin)


def _pid_is_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    stat_path = Path("/proc") / str(pid) / "stat"
    if stat_path.exists():
        try:
            parts = stat_path.read_text(encoding="utf-8").split()
        except OSError:
            parts = []
        if len(parts) > 2 and parts[2] == "Z":
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _record_matches_scope(data: dict, scope_path: Path) -> bool:
    try:
        recorded = Path(str(data.get("scopePath") or "")).resolve()
    except OSError:
        return False
    return recorded == scope_path.resolve()


def code_server_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in CODE_SERVER_ENV_REMOVE:
        env.pop(name, None)
    for name in list(env):
        if name.startswith(CODE_SERVER_ENV_REMOVE_PREFIXES):
            env.pop(name, None)
    if "PATH" in env:
        env["PATH"] = os.pathsep.join(
            part
            for part in env["PATH"].split(os.pathsep)
            if not any(excluded in part for excluded in CODE_SERVER_PATH_EXCLUDE_PARTS)
        )
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
    if not _editor_record_is_alive(data):
        path.unlink(missing_ok=True)
        return None
    scope_path = data.get("scopePath")
    if scope_path:
        try:
            ensure_under_project(project, Path(str(scope_path)).resolve())
        except ValidationError:
            return None
    port = data.get("port")
    if not isinstance(port, int) or port <= 0:
        return None
    return data


def _editor_record_is_alive(data: dict) -> bool:
    port = data.get("port")
    if isinstance(port, int) and port > 0 and _port_is_open(port):
        return True
    return _pid_is_alive(data.get("pid"))


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _wait_for_editor_start(port: int, process: subprocess.Popen, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(port):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    return _port_is_open(port)


def _read_log_tail(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return "no log output"
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return "no log output"
    return text[-max_chars:]


def editor_id_from_host(host: str | None) -> str | None:
    if not host:
        return None
    hostname = host.split(":", 1)[0].lower()
    first_label = hostname.split(".", 1)[0]
    if first_label.startswith("editor-"):
        return first_label
    return None


def find_code_server(project: Project) -> str | None:
    repo_local = project.root_path / ".tools" / "code-server" / "node_modules" / ".bin" / "code-server"
    if repo_local.exists():
        return str(repo_local)
    package_local = Path(__file__).resolve().parents[1] / ".tools" / "code-server" / "node_modules" / ".bin" / "code-server"
    if package_local.exists():
        return str(package_local)
    global_bin = shutil.which("code-server")
    if global_bin and not _is_vscode_server_path(Path(global_bin)):
        return global_bin
    return None


def _is_vscode_server_path(path: Path) -> bool:
    normalized = path.resolve().as_posix()
    return any(excluded in normalized for excluded in CODE_SERVER_PATH_EXCLUDE_PARTS)
