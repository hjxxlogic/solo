#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_ROOT / ".venv"
TOOLS_DIR = REPO_ROOT / ".tools"
CODE_SERVER_DIR = TOOLS_DIR / "code-server"
NPM_LOG_DIR = Path.home() / ".npm" / "_logs"


def run(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def run_with_output(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if env and env.get("https_proxy"):
        print(f"$ https_proxy={env['https_proxy']} {' '.join(command)}", flush=True)
    else:
        print(f"$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv(python_bin: str) -> None:
    if not venv_python().exists():
        run([python_bin, "-m", "venv", str(VENV_DIR)])
    run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(venv_python()), "-m", "pip", "install", "-e", "."])


def code_server_bin() -> Path:
    if os.name == "nt":
        return CODE_SERVER_DIR / "node_modules" / ".bin" / "code-server.cmd"
    return CODE_SERVER_DIR / "node_modules" / ".bin" / "code-server"


def code_server_install_proxy(explicit_proxy: str | None) -> str | None:
    if explicit_proxy:
        return explicit_proxy
    host_ip = os.environ.get("HOST_IP")
    if host_ip:
        return f"http://{host_ip}:10809"
    return None


def npm_install_env(proxy: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if proxy:
        env["https_proxy"] = proxy
    return env


def latest_npm_log_text() -> str:
    if not NPM_LOG_DIR.exists():
        return ""
    logs = sorted(NPM_LOG_DIR.glob("*-debug-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not logs:
        return ""
    try:
        return logs[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def explain_code_server_install_failure(output: str) -> None:
    detail = output + "\n" + latest_npm_log_text()
    print("")
    print("code-server installation failed.")
    if "gssapi/gssapi.h" in detail or "kerberos" in detail:
        print("")
        print("Detected missing Kerberos/GSSAPI build headers required by the kerberos native module.")
        print("On Debian/Ubuntu/WSL, install system build dependencies, then rerun this script:")
        print("")
        print("  sudo apt-get update")
        print("  sudo apt-get install -y build-essential python3 make g++ libkrb5-dev")
        print("  scripts/install_dependencies.sh")
    else:
        print("Check the npm log under ~/.npm/_logs for the native module build error.")


def ensure_code_server(skip: bool = False, proxy: str | None = None) -> None:
    if skip:
        print("skip code-server installation")
        return
    if command_exists("code-server"):
        print(f"code-server found: {shutil.which('code-server')}")
        return
    if code_server_bin().exists():
        print(f"code-server found: {code_server_bin()}")
        return
    if not command_exists("npm"):
        raise SystemExit("npm is required to install code-server; install Node.js/npm first")
    CODE_SERVER_DIR.mkdir(parents=True, exist_ok=True)
    result = run_with_output(
        ["npm", "install", "code-server", "--prefix", str(CODE_SERVER_DIR)],
        env=npm_install_env(proxy),
    )
    if result.returncode != 0:
        explain_code_server_install_failure(result.stdout + "\n" + result.stderr)
        raise SystemExit(result.returncode)
    print(f"code-server installed: {code_server_bin()}")


def check_external_tools(skip_code_server: bool = False) -> None:
    missing: list[str] = []
    for command in ("git",):
        if not command_exists(command):
            missing.append(command)
    if missing:
        raise SystemExit(f"missing required tools: {', '.join(missing)}")
    if not skip_code_server and not (command_exists("code-server") or code_server_bin().exists()):
        raise SystemExit("code-server installation did not produce an executable")
    if not command_exists("codex"):
        print("warning: codex CLI was not found; Codex-backed workflow actions will fail until installed")


def install(args: argparse.Namespace) -> None:
    ensure_venv(args.python)
    ensure_code_server(
        skip=args.skip_code_server,
        proxy=code_server_install_proxy(args.code_server_proxy),
    )
    check_external_tools(skip_code_server=args.skip_code_server)
    print("")
    print("SOLO dependencies are ready.")
    print(f"Python: {venv_python()}")
    if code_server_bin().exists():
        print(f"code-server: {code_server_bin()}")
    elif shutil.which("code-server"):
        print(f"code-server: {shutil.which('code-server')}")
    print("")
    print("Run:")
    print("  .venv/bin/solo serve . --port 8765")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install SOLO development/runtime dependencies.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to create .venv.")
    parser.add_argument("--skip-code-server", action="store_true", help="Only install Python dependencies.")
    parser.add_argument(
        "--code-server-proxy",
        help="Proxy used only for npm code-server installation. Defaults to http://$HOST_IP:10809 when HOST_IP is set.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    install(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
