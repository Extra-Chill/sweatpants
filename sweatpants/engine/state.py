"""SQLite state persistence for jobs, modules, and results."""

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import aiosqlite

from sweatpants.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    entrypoint TEXT NOT NULL,
    inputs TEXT,
    settings TEXT,
    capabilities TEXT,
    installed_at TEXT NOT NULL,
    path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    inputs TEXT,
    settings TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    checkpoint TEXT,
    FOREIGN KEY (module_id) REFERENCES modules(id)
);

CREATE TABLE IF NOT EXISTS job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS job_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_module ON jobs(module_id);
CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_job_results_job ON job_results(job_id);
"""


async def init_database() -> None:
    """Initialize the database schema."""
    settings = get_settings()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


class StateManager:
    """Manages persistent state in SQLite."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._db_path = str(self.settings.db_path)

    async def save_module(
        self,
        module_id: str,
        name: str,
        version: str,
        description: str,
        entrypoint: str,
        inputs: list[dict],
        settings: list[dict],
        capabilities: list[str],
        path: str,
    ) -> None:
        """Save or update a module record."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO modules
                (id, name, version, description, entrypoint, inputs, settings, capabilities, installed_at, path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    module_id,
                    name,
                    version,
                    description,
                    entrypoint,
                    json.dumps(inputs),
                    json.dumps(settings),
                    json.dumps(capabilities),
                    datetime.now(timezone.utc).isoformat(),
                    path,
                ),
            )
            await db.commit()

    async def get_module(self, module_id: str) -> Optional[dict]:
        """Get a module by ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM modules WHERE id = ?", (module_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "version": row["version"],
                        "description": row["description"],
                        "entrypoint": row["entrypoint"],
                        "inputs": json.loads(row["inputs"]) if row["inputs"] else [],
                        "settings": json.loads(row["settings"]) if row["settings"] else [],
                        "capabilities": (
                            json.loads(row["capabilities"]) if row["capabilities"] else []
                        ),
                        "installed_at": row["installed_at"],
                        "path": row["path"],
                    }
                return None

    async def list_modules(self) -> list[dict]:
        """List all installed modules."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM modules ORDER BY name") as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "version": row["version"],
                        "description": row["description"],
                        "capabilities": (
                            json.loads(row["capabilities"]) if row["capabilities"] else []
                        ),
                    }
                    for row in rows
                ]

    async def delete_module(self, module_id: str) -> bool:
        """Delete a module record."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM modules WHERE id = ?", (module_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def create_job(
        self,
        module_id: str,
        inputs: dict[str, Any],
        settings: dict[str, Any],
    ) -> str:
        """Create a new job record."""
        job_id = str(uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (id, module_id, status, inputs, settings, created_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (
                    job_id,
                    module_id,
                    json.dumps(inputs),
                    json.dumps(settings),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
        return job_id

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        checkpoint: Optional[dict] = None,
    ) -> None:
        """Update job status."""
        async with aiosqlite.connect(self._db_path) as db:
            now = datetime.now(timezone.utc).isoformat()

            if status == "running":
                await db.execute(
                    "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, job_id),
                )
            elif status in ("completed", "failed", "stopped"):
                await db.execute(
                    "UPDATE jobs SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                    (status, now, error, job_id),
                )
            else:
                await db.execute(
                    "UPDATE jobs SET status = ? WHERE id = ?",
                    (status, job_id),
                )

            if checkpoint is not None:
                await db.execute(
                    "UPDATE jobs SET checkpoint = ? WHERE id = ?",
                    (json.dumps(checkpoint), job_id),
                )

            await db.commit()

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get a job by ID (supports partial ID matching)."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM jobs WHERE id = ? OR id LIKE ?",
                (job_id, f"{job_id}%"),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "module_id": row["module_id"],
                        "status": row["status"],
                        "inputs": json.loads(row["inputs"]) if row["inputs"] else {},
                        "settings": json.loads(row["settings"]) if row["settings"] else {},
                        "created_at": row["created_at"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "error": row["error"],
                        "checkpoint": (
                            json.loads(row["checkpoint"]) if row["checkpoint"] else None
                        ),
                    }
                return None

    async def _resolve_job_id(self, job_id: str) -> Optional[str]:
        """Resolve a partial job ID to full ID."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id FROM jobs WHERE id = ? OR id LIKE ? LIMIT 1",
                (job_id, f"{job_id}%"),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def list_jobs(self, status: Optional[str] = None) -> list[dict]:
        """List jobs, optionally filtered by status."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                query = "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC"
                cursor = await db.execute(query, (status,))
            else:
                query = "SELECT * FROM jobs ORDER BY created_at DESC"
                cursor = await db.execute(query)

            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "module_id": row["module_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                }
                for row in rows
            ]

    async def get_resumable_jobs(self) -> list[dict]:
        """Get jobs that were running and can be resumed."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "module_id": row["module_id"],
                        "inputs": json.loads(row["inputs"]) if row["inputs"] else {},
                        "settings": json.loads(row["settings"]) if row["settings"] else {},
                        "checkpoint": (
                            json.loads(row["checkpoint"]) if row["checkpoint"] else None
                        ),
                    }
                    for row in rows
                ]

    async def add_log(self, job_id: str, level: str, message: str) -> None:
        """Add a log entry for a job."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO job_logs (job_id, level, message, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, level, message, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def get_logs(
        self, job_id: str, limit: int = 100, after_id: Optional[int] = None
    ) -> list[dict]:
        """Get log entries for a job."""
        full_job_id = await self._resolve_job_id(job_id)
        if not full_job_id:
            return []

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            if after_id:
                query = """
                    SELECT * FROM job_logs
                    WHERE job_id = ? AND id > ?
                    ORDER BY id LIMIT ?
                """
                cursor = await db.execute(query, (full_job_id, after_id, limit))
            else:
                query = """
                    SELECT * FROM job_logs
                    WHERE job_id = ?
                    ORDER BY id DESC LIMIT ?
                """
                cursor = await db.execute(query, (full_job_id, limit))

            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "level": row["level"],
                    "message": row["message"],
                    "timestamp": row["timestamp"],
                }
                for row in (reversed(rows) if not after_id else rows)
            ]

    async def add_result(self, job_id: str, data: dict[str, Any]) -> None:
        """Add a result entry for a job."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO job_results (job_id, data, created_at)
                VALUES (?, ?, ?)
                """,
                (job_id, json.dumps(data), datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def get_results(self, job_id: str, limit: int = 1000) -> list[dict]:
        """Get results for a job."""
        full_job_id = await self._resolve_job_id(job_id)
        if not full_job_id:
            return []

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM job_results WHERE job_id = ? ORDER BY id LIMIT ?",
                (full_job_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "data": json.loads(row["data"]),
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]

    async def get_result_count(self, job_id: str) -> int:
        """Get the count of results for a job."""
        full_job_id = await self._resolve_job_id(job_id)
        if not full_job_id:
            return 0

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM job_results WHERE job_id = ?",
                (full_job_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
