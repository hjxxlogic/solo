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
