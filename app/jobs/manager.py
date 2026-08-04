import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    stage TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    file_path TEXT NOT NULL,
    result_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class JobManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_job(self, file_path: str, job_id: Optional[str] = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, stage, progress, file_path, result_path, "
                "error, created_at, updated_at) VALUES (?, 'queued', NULL, 0, ?, NULL, NULL, ?, ?)",
                (job_id, file_path, now, now),
            )
        return job_id

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress: Optional[int] = None,
        result_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        fields = {
            "status": status, "stage": stage, "progress": progress,
            "result_path": result_path, "error": error,
        }
        set_fields = {k: v for k, v in fields.items() if v is not None}
        if not set_fields:
            return
        set_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{k} = ?" for k in set_fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*set_fields.values(), job_id),
            )

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
