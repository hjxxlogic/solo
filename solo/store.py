from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .models import JsonDict, Run


SCHEMA = """
create table if not exists runs (
    id text primary key,
    project_id text not null,
    workflow_id text not null,
    action_id text not null,
    status text not null,
    data text not null,
    created_at text not null,
    updated_at text not null
);

create table if not exists codex_sessions (
    id text primary key,
    project_id text not null,
    status text not null,
    first_prompt text,
    first_prompt_at text,
    cwd text,
    transcript_path text,
    model text,
    started_at text,
    ended_at text,
    last_event text not null,
    last_event_at text not null,
    turn_count integer not null default 0,
    data text not null
);
"""


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.executescript(SCHEMA)

    def save_run(self, run: Run) -> None:
        data = run.to_dict()
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    insert into runs (id, project_id, workflow_id, action_id, status, data, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do update set
                        status = excluded.status,
                        data = excluded.data,
                        updated_at = excluded.updated_at
                    """,
                    (
                        run.id,
                        run.project_id,
                        run.workflow_id,
                        run.action_id,
                        run.status,
                        json.dumps(data, sort_keys=True),
                        run.created_at,
                        data["updatedAt"],
                    ),
                )

    def get_run(self, run_id: str) -> Run | None:
        with closing(self._connect()) as conn:
            row = conn.execute("select data from runs where id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return Run.from_dict(json.loads(str(row["data"])))

    def list_runs(self, project_id: str | None = None) -> list[JsonDict]:
        sql = "select data from runs"
        params: tuple[str, ...] = ()
        if project_id:
            sql += " where project_id = ?"
            params = (project_id,)
        sql += " order by created_at desc"
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(str(row["data"])) for row in rows]

    def record_codex_session_event(
        self,
        *,
        project_id: str,
        session_id: str,
        event_name: str,
        cwd: str | None = None,
        transcript_path: str | None = None,
        model: str | None = None,
        prompt: str | None = None,
        payload: JsonDict | None = None,
        timestamp: str,
    ) -> JsonDict:
        existing = self.get_codex_session(session_id)
        first_prompt = existing.get("firstPrompt") if existing else None
        first_prompt_at = existing.get("firstPromptAt") if existing else None
        started_at = existing.get("startedAt") if existing else None
        ended_at = existing.get("endedAt") if existing else None
        turn_count = int(existing.get("turnCount") or 0) if existing else 0
        status = str(existing.get("status") or "active") if existing else "active"

        if event_name == "SessionStart" and not started_at:
            started_at = timestamp
        if event_name == "UserPromptSubmit":
            turn_count += 1
            if not first_prompt:
                first_prompt = prompt_summary(prompt or "")
                first_prompt_at = timestamp
            if status != "ended":
                status = "active"
        if event_name == "Stop":
            status = "ended"
            ended_at = timestamp

        data: JsonDict = {
            "id": session_id,
            "projectId": project_id,
            "status": status,
            "ended": status == "ended",
            "firstPrompt": first_prompt,
            "firstPromptAt": first_prompt_at,
            "cwd": cwd or (existing.get("cwd") if existing else None),
            "transcriptPath": transcript_path or (existing.get("transcriptPath") if existing else None),
            "model": model or (existing.get("model") if existing else None),
            "startedAt": started_at,
            "endedAt": ended_at,
            "lastEvent": event_name,
            "lastEventAt": timestamp,
            "turnCount": turn_count,
            "updatedAt": timestamp,
        }
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    insert into codex_sessions (
                        id, project_id, status, first_prompt, first_prompt_at, cwd,
                        transcript_path, model, started_at, ended_at, last_event,
                        last_event_at, turn_count, data
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do update set
                        project_id = excluded.project_id,
                        status = excluded.status,
                        first_prompt = excluded.first_prompt,
                        first_prompt_at = excluded.first_prompt_at,
                        cwd = excluded.cwd,
                        transcript_path = excluded.transcript_path,
                        model = excluded.model,
                        started_at = excluded.started_at,
                        ended_at = excluded.ended_at,
                        last_event = excluded.last_event,
                        last_event_at = excluded.last_event_at,
                        turn_count = excluded.turn_count,
                        data = excluded.data
                    """,
                    (
                        session_id,
                        project_id,
                        status,
                        first_prompt,
                        first_prompt_at,
                        data["cwd"],
                        data["transcriptPath"],
                        data["model"],
                        started_at,
                        ended_at,
                        event_name,
                        timestamp,
                        turn_count,
                        json.dumps({**data, "raw": payload or {}}, sort_keys=True),
                    ),
                )
        return data

    def get_codex_session(self, session_id: str) -> JsonDict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "select data from codex_sessions where id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        data = json.loads(str(row["data"]))
        data.pop("raw", None)
        return data

    def list_codex_sessions(self, project_id: str) -> list[JsonDict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                select data from codex_sessions
                where project_id = ?
                order by last_event_at desc
                """,
                (project_id,),
            ).fetchall()
        sessions = [json.loads(str(row["data"])) for row in rows]
        for session in sessions:
            session.pop("raw", None)
        return sessions


def prompt_summary(prompt: str, limit: int = 80) -> str:
    normalized = " ".join(prompt.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit]
