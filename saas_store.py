from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SQLiteStore:
    """SQLite persistence for API keys, transcript jobs, and batches."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    languages_json TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    processing_items INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transcript_jobs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    video_input TEXT NOT NULL,
                    video_id TEXT,
                    languages_json TEXT NOT NULL,
                    languages_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_language TEXT,
                    result_source TEXT,
                    result_text TEXT,
                    error_message TEXT,
                    cached INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES batches(id)
                );

                CREATE INDEX IF NOT EXISTS idx_transcript_jobs_batch_id
                    ON transcript_jobs(batch_id);
                CREATE INDEX IF NOT EXISTS idx_transcript_jobs_cache_lookup
                    ON transcript_jobs(video_id, languages_key, status);
                """
            )

    def ensure_api_key(self, key: str, name: str, created_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO api_keys (key, name, active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (key, name, created_at),
            )

    def create_api_key(
        self,
        name: str,
        created_at: str,
        key: str | None = None,
    ) -> dict[str, Any]:
        api_key = key or f"ghost_{secrets.token_urlsafe(24)}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (key, name, active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (api_key, name, created_at),
            )
        return {
            "key": api_key,
            "name": name,
            "active": True,
            "created_at": created_at,
        }

    def deactivate_api_key(self, key: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET active = 0 WHERE key = ?",
                (key,),
            )
        return cursor.rowcount > 0

    def list_api_keys(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT key, name, active, created_at
                FROM api_keys
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def is_api_key_active(self, key: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT active FROM api_keys WHERE key = ?",
                (key,),
            ).fetchone()
        return bool(row and row["active"])

    def create_batch(self, batch: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO batches (
                    id,
                    status,
                    languages_json,
                    total_items,
                    completed_items,
                    failed_items,
                    processing_items,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch["id"],
                    batch["status"],
                    batch["languages_json"],
                    batch["total_items"],
                    batch["completed_items"],
                    batch["failed_items"],
                    batch["processing_items"],
                    batch["created_at"],
                    batch["updated_at"],
                ),
            )

    def create_job(self, job: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO transcript_jobs (
                    id,
                    batch_id,
                    video_input,
                    video_id,
                    languages_json,
                    languages_key,
                    status,
                    result_language,
                    result_source,
                    result_text,
                    error_message,
                    cached,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["id"],
                    job["batch_id"],
                    job["video_input"],
                    job["video_id"],
                    job["languages_json"],
                    job["languages_key"],
                    job["status"],
                    job["result_language"],
                    job["result_source"],
                    job["result_text"],
                    job["error_message"],
                    int(job["cached"]),
                    job["created_at"],
                    job["updated_at"],
                ),
            )

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, status, languages_json, total_items, completed_items,
                       failed_items, processing_items, created_at, updated_at
                FROM batches
                WHERE id = ?
                """,
                (batch_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, batch_id, video_input, video_id, languages_json,
                       languages_key, status, result_language, result_source,
                       result_text, error_message, cached, created_at, updated_at
                FROM transcript_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_batch_jobs(self, batch_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, batch_id, video_input, video_id, languages_json,
                       languages_key, status, result_language, result_source,
                       result_text, error_message, cached, created_at, updated_at
                FROM transcript_jobs
                WHERE batch_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (batch_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def find_cached_job(self, video_id: str, languages_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, batch_id, video_input, video_id, languages_json,
                       languages_key, status, result_language, result_source,
                       result_text, error_message, cached, created_at, updated_at
                FROM transcript_jobs
                WHERE video_id = ?
                  AND languages_key = ?
                  AND status = 'completed'
                  AND result_text IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (video_id, languages_key),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_job(self, job_id: str, updates: dict[str, Any]) -> None:
        if not updates:
            return

        assignments = ", ".join(f"{column} = ?" for column in updates)
        values = list(updates.values()) + [job_id]
        with self.connect() as connection:
            connection.execute(
                f"UPDATE transcript_jobs SET {assignments} WHERE id = ?",
                values,
            )

    def refresh_batch(self, batch_id: str, updated_at: str) -> None:
        with self.connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_items,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_items,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_items,
                    SUM(CASE WHEN status IN ('queued', 'processing') THEN 1 ELSE 0 END) AS processing_items
                FROM transcript_jobs
                WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()

            total_items = int(counts["total_items"] or 0)
            completed_items = int(counts["completed_items"] or 0)
            failed_items = int(counts["failed_items"] or 0)
            processing_items = int(counts["processing_items"] or 0)

            if processing_items > 0:
                status = "processing"
            elif failed_items == total_items and total_items > 0:
                status = "failed"
            elif failed_items > 0:
                status = "completed_with_errors"
            else:
                status = "completed"

            connection.execute(
                """
                UPDATE batches
                SET status = ?,
                    total_items = ?,
                    completed_items = ?,
                    failed_items = ?,
                    processing_items = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    total_items,
                    completed_items,
                    failed_items,
                    processing_items,
                    updated_at,
                    batch_id,
                ),
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {key: row[key] for key in row.keys()}
