from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import SoloError
from .models import JsonDict, now_iso
from .project import ensure_project
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m solo.codex_hook")
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo")
    args = parser.parse_args(argv)

    try:
        payload = _read_payload()
        repo = Path(args.repo).resolve() if args.repo else _repo_from_payload(payload)
        project = ensure_project(repo)
        store = Store(project.runtime_dir / "db.sqlite")
        session_id = _session_id(payload)
        store.record_codex_session_event(
            project_id=project.id,
            session_id=session_id,
            event_name=args.event,
            cwd=_string_value(payload, "cwd", "working_directory", "workingDirectory"),
            transcript_path=_string_value(payload, "transcript_path", "transcriptPath"),
            model=_string_value(payload, "model"),
            prompt=_prompt(payload),
            payload=payload,
            timestamp=now_iso(),
        )
        return 0
    except Exception as exc:
        print(f"solo codex hook: {exc}", file=sys.stderr)
        return 0


def _read_payload() -> JsonDict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {"value": data}


def _repo_from_payload(payload: JsonDict) -> Path:
    cwd = _string_value(payload, "cwd", "working_directory", "workingDirectory")
    if cwd:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
        return Path(cwd).resolve()
    return Path.cwd().resolve()


def _session_id(payload: JsonDict) -> str:
    direct = _string_value(payload, "session_id", "sessionId", "conversation_id", "conversationId")
    if direct:
        return direct
    nested = payload.get("session")
    if isinstance(nested, dict):
        value = _string_value(nested, "id", "session_id", "sessionId")
        if value:
            return value
    raise SoloError("hook payload does not include a session id")


def _prompt(payload: JsonDict) -> str | None:
    direct = _string_value(payload, "prompt", "user_prompt", "userPrompt", "message")
    if direct:
        return direct
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            text = _message_text(message)
            if text:
                return text
    return None


def _message_text(message: Any) -> str | None:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return None
    direct = _string_value(message, "text", "content")
    if direct:
        return direct
    content = message.get("content")
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = _string_value(item, "text", "input_text")
                if text:
                    chunks.append(text)
        return "\n".join(chunks) if chunks else None
    return None


def _string_value(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
