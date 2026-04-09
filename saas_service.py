from __future__ import annotations

import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ghost_yt_downloader import (
    TranscriptDownloadError,
    download_transcript,
    extract_video_id,
)
from saas_store import SQLiteStore


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ServiceConfig:
    max_workers: int = 4
    auto_process: bool = True
    max_batch_size: int = 200


class TranscriptSaaSService:
    """Coordinates API keys, transcript jobs, and batch processing."""

    def __init__(
        self,
        store: SQLiteStore,
        config: ServiceConfig | None = None,
    ) -> None:
        self._store = store
        self._config = config or ServiceConfig()
        self._executor = (
            ThreadPoolExecutor(max_workers=self._config.max_workers)
            if self._config.auto_process
            else None
        )

    @property
    def max_batch_size(self) -> int:
        return self._config.max_batch_size

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=False)

    def ensure_default_api_key(self, api_key: str, name: str = "default") -> None:
        self._store.ensure_api_key(api_key, name=name, created_at=_utcnow())

    def create_api_key(self, name: str, key: str | None = None) -> dict[str, Any]:
        return self._store.create_api_key(name=name, key=key, created_at=_utcnow())

    def list_api_keys(self) -> list[dict[str, Any]]:
        return self._store.list_api_keys()

    def deactivate_api_key(self, key: str) -> bool:
        return self._store.deactivate_api_key(key)

    def is_api_key_valid(self, key: str) -> bool:
        return self._store.is_api_key_active(key)

    def create_transcript_request(
        self,
        video: str,
        languages: Iterable[str] | None = None,
        batch_id: str | None = None,
        *,
        refresh_batch: bool = True,
    ) -> dict[str, Any]:
        normalized_languages = self._normalize_languages(languages)
        languages_json = json.dumps(normalized_languages)
        languages_key = ",".join(normalized_languages)
        job_id = self._generate_id("tr")
        now = _utcnow()

        try:
            video_id = extract_video_id(video)
        except ValueError as exc:
            self._store.create_job(
                {
                    "id": job_id,
                    "batch_id": batch_id,
                    "video_input": video,
                    "video_id": None,
                    "languages_json": languages_json,
                    "languages_key": languages_key,
                    "status": "failed",
                    "result_language": None,
                    "result_source": None,
                    "result_text": None,
                    "error_message": str(exc),
                    "cached": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if batch_id is not None and refresh_batch:
                self._store.refresh_batch(batch_id, updated_at=now)
            created_job = self.get_transcript_request(job_id)
            assert created_job is not None
            return created_job

        cached_job = self._store.find_cached_job(video_id, languages_key)
        if cached_job:
            self._store.create_job(
                {
                    "id": job_id,
                    "batch_id": batch_id,
                    "video_input": video,
                    "video_id": video_id,
                    "languages_json": languages_json,
                    "languages_key": languages_key,
                    "status": "completed",
                    "result_language": cached_job["result_language"],
                    "result_source": cached_job["result_source"],
                    "result_text": cached_job["result_text"],
                    "error_message": None,
                    "cached": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            if batch_id is not None and refresh_batch:
                self._store.refresh_batch(batch_id, updated_at=now)
            created_job = self.get_transcript_request(job_id)
            assert created_job is not None
            return created_job

        self._store.create_job(
            {
                "id": job_id,
                "batch_id": batch_id,
                "video_input": video,
                "video_id": video_id,
                "languages_json": languages_json,
                "languages_key": languages_key,
                "status": "queued",
                "result_language": None,
                "result_source": None,
                "result_text": None,
                "error_message": None,
                "cached": False,
                "created_at": now,
                "updated_at": now,
            }
        )
        if batch_id is not None and refresh_batch:
            self._store.refresh_batch(batch_id, updated_at=now)

        if self._executor is not None:
            self._executor.submit(self.process_transcript_request, job_id)

        created_job = self.get_transcript_request(job_id)
        assert created_job is not None
        return created_job

    def process_transcript_request(self, transcript_id: str) -> dict[str, Any]:
        job = self._store.get_job(transcript_id)
        if not job:
            raise KeyError(f"Transcript request not found: {transcript_id}")

        if job["status"] != "queued":
            return self._serialize_job(job)

        now = _utcnow()
        self._store.update_job(
            transcript_id,
            {
                "status": "processing",
                "updated_at": now,
            },
        )
        if job["batch_id"]:
            self._store.refresh_batch(job["batch_id"], updated_at=now)

        languages = json.loads(job["languages_json"])
        try:
            result = download_transcript(job["video_input"], preferred_languages=languages)
        except TranscriptDownloadError as exc:
            finished_at = _utcnow()
            self._store.update_job(
                transcript_id,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "updated_at": finished_at,
                },
            )
            if job["batch_id"]:
                self._store.refresh_batch(job["batch_id"], updated_at=finished_at)
            failed_job = self.get_transcript_request(transcript_id)
            assert failed_job is not None
            return failed_job

        finished_at = _utcnow()
        self._store.update_job(
            transcript_id,
            {
                "status": "completed",
                "video_id": result.video_id,
                "result_language": result.language,
                "result_source": result.source,
                "result_text": result.text,
                "error_message": None,
                "updated_at": finished_at,
            },
        )
        if job["batch_id"]:
            self._store.refresh_batch(job["batch_id"], updated_at=finished_at)
        completed_job = self.get_transcript_request(transcript_id)
        assert completed_job is not None
        return completed_job

    def create_batch(
        self,
        videos: list[str],
        languages: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        normalized_languages = self._normalize_languages(languages)
        now = _utcnow()
        batch_id = self._generate_id("bat")
        self._store.create_batch(
            {
                "id": batch_id,
                "status": "queued",
                "languages_json": json.dumps(normalized_languages),
                "total_items": len(videos),
                "completed_items": 0,
                "failed_items": 0,
                "processing_items": 0,
                "created_at": now,
                "updated_at": now,
            }
        )

        for video in videos:
            self.create_transcript_request(
                video,
                normalized_languages,
                batch_id=batch_id,
                refresh_batch=False,
            )

        self._store.refresh_batch(batch_id, updated_at=_utcnow())
        batch = self.get_batch(batch_id)
        assert batch is not None
        return batch

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        batch = self._store.get_batch(batch_id)
        if not batch:
            return None
        return self._serialize_batch(batch)

    def get_batch_items(self, batch_id: str) -> list[dict[str, Any]]:
        return [self._serialize_job(job) for job in self._store.list_batch_jobs(batch_id)]

    def get_transcript_request(self, transcript_id: str) -> dict[str, Any] | None:
        job = self._store.get_job(transcript_id)
        if not job:
            return None
        return self._serialize_job(job)

    def _serialize_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": batch["id"],
            "status": batch["status"],
            "languages": json.loads(batch["languages_json"]),
            "total_items": batch["total_items"],
            "completed_items": batch["completed_items"],
            "failed_items": batch["failed_items"],
            "processing_items": batch["processing_items"],
            "created_at": batch["created_at"],
            "updated_at": batch["updated_at"],
        }

    def _serialize_job(self, job: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": job["id"],
            "batch_id": job["batch_id"],
            "status": job["status"],
            "video_input": job["video_input"],
            "video_id": job["video_id"],
            "languages": json.loads(job["languages_json"]),
            "language": job["result_language"],
            "source": job["result_source"],
            "text": job["result_text"],
            "error_message": job["error_message"],
            "cached": bool(job["cached"]),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

    @staticmethod
    def _normalize_languages(languages: Iterable[str] | None) -> tuple[str, ...]:
        if not languages:
            return ("es", "en")

        normalized = tuple(lang.strip().lower() for lang in languages if lang.strip())
        return normalized or ("es", "en")

    @staticmethod
    def _generate_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"
