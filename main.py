"""FastAPI service for single and batch YouTube transcript processing."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from ghost_yt_downloader import TranscriptDownloadError, download_transcript
from saas_service import ServiceConfig, TranscriptSaaSService
from saas_store import SQLiteStore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class HealthResponse(BaseModel):
    status: str = Field(description="Service health status.", examples=["ok"])


class TranscriptResponse(BaseModel):
    video_id: str = Field(description="Resolved YouTube video ID.", examples=["dQw4w9WgXcQ"])
    language: str | None = Field(
        description="Language actually returned by the subtitle source.",
        examples=["es"],
    )
    source: str = Field(
        description="Subtitle provider path selected internally.",
        examples=["yt_dlp_auto"],
    )
    text: str = Field(
        description="Normalized transcript text in a single running text string.",
        examples=["texto corrido aqui"],
    )


class TranscriptCreateRequest(BaseModel):
    video: str = Field(
        description="YouTube video ID or URL to process.",
        examples=["dQw4w9WgXcQ"],
    )
    languages: list[str] = Field(
        default_factory=lambda: ["es", "en"],
        description="Ordered preferred languages. Used for subtitle selection and cache keying.",
        examples=[["es", "en"]],
    )


class TranscriptJobResponse(BaseModel):
    id: str = Field(description="Transcript job ID.", examples=["tr_123abc456def"])
    batch_id: str | None = Field(
        description="Parent batch ID when created via /v1/batches.",
        examples=["bat_123abc456def"],
    )
    status: str = Field(
        description="Job lifecycle state: queued, processing, completed, or failed.",
        examples=["queued"],
    )
    video_input: str = Field(
        description="Original input string sent by the client.",
        examples=["https://youtu.be/dQw4w9WgXcQ"],
    )
    video_id: str | None = Field(
        description="Normalized YouTube video ID if extraction succeeded.",
        examples=["dQw4w9WgXcQ"],
    )
    languages: list[str] = Field(
        description="Ordered language preference used for this job.",
        examples=[["es", "en"]],
    )
    language: str | None = Field(
        description="Language actually returned by the transcript provider.",
        examples=["es"],
    )
    source: str | None = Field(
        description="Provider/source label used internally.",
        examples=["yt_dlp_manual"],
    )
    text: str | None = Field(
        description="Normalized transcript text. Null until completion or on failure.",
        examples=["texto corrido aqui"],
    )
    error_message: str | None = Field(
        description="Failure reason when status is failed.",
        examples=["No se pudo extraer un video ID válido desde: bad"],
    )
    cached: bool = Field(
        description="True when the result was reused from a previously completed transcript.",
        examples=[False],
    )
    created_at: str = Field(
        description="Job creation timestamp in ISO 8601 UTC.",
        examples=["2026-04-08T20:00:00+00:00"],
    )
    updated_at: str = Field(
        description="Last update timestamp in ISO 8601 UTC.",
        examples=["2026-04-08T20:00:02+00:00"],
    )


class BatchCreateRequest(BaseModel):
    videos: list[str] = Field(
        description="List of YouTube video IDs or URLs to enqueue in one batch.",
        examples=[["dQw4w9WgXcQ", "https://www.youtube.com/watch?v=5X26m52lMwU"]],
    )
    languages: list[str] = Field(
        default_factory=lambda: ["es", "en"],
        description="Ordered preferred languages shared by all items in the batch.",
        examples=[["es", "en"]],
    )


class BatchResponse(BaseModel):
    id: str = Field(description="Batch ID.", examples=["bat_123abc456def"])
    status: str = Field(
        description=(
            "Batch lifecycle state: processing, completed, failed, or completed_with_errors."
        ),
        examples=["processing"],
    )
    languages: list[str] = Field(
        description="Ordered language preference applied to all items in the batch.",
        examples=[["es", "en"]],
    )
    total_items: int = Field(description="Total number of items in the batch.", examples=[2])
    completed_items: int = Field(
        description="Number of batch items completed successfully.",
        examples=[1],
    )
    failed_items: int = Field(
        description="Number of batch items that failed.",
        examples=[0],
    )
    processing_items: int = Field(
        description="Number of child jobs still queued or processing.",
        examples=[1],
    )
    created_at: str = Field(
        description="Batch creation timestamp in ISO 8601 UTC.",
        examples=["2026-04-08T20:00:00+00:00"],
    )
    updated_at: str = Field(
        description="Last update timestamp in ISO 8601 UTC.",
        examples=["2026-04-08T20:00:02+00:00"],
    )


class BatchItemsResponse(BaseModel):
    batch_id: str = Field(description="Parent batch ID.", examples=["bat_123abc456def"])
    items: list[TranscriptJobResponse] = Field(
        description="All transcript jobs created for the batch in creation order."
    )


def get_service(request: Request) -> TranscriptSaaSService:
    return request.app.state.transcript_service


api_key_security = Security(api_key_header)
service_dependency = Depends(get_service)


def require_api_key(
    api_key: str | None = api_key_security,
    service: TranscriptSaaSService = service_dependency,
) -> str:
    if not api_key or not service.is_api_key_valid(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente",
        )
    return api_key


api_key_dependency = Depends(require_api_key)


def create_default_service() -> TranscriptSaaSService:
    db_path = Path(os.getenv("GHOST_DB_PATH", "ghost_saas.db"))
    default_api_key = os.getenv("GHOST_API_KEY", "ghost-dev-key")
    max_workers = int(os.getenv("GHOST_WORKER_COUNT", "4"))
    max_batch_size = int(os.getenv("GHOST_MAX_BATCH_SIZE", "200"))

    store = SQLiteStore(db_path)
    store.init_db()

    service = TranscriptSaaSService(
        store,
        ServiceConfig(
            max_workers=max_workers,
            auto_process=True,
            max_batch_size=max_batch_size,
        ),
    )
    service.ensure_default_api_key(default_api_key)
    return service


def create_app(service: TranscriptSaaSService | None = None) -> FastAPI:
    managed_service = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        transcript_service = service or create_default_service()
        app.state.transcript_service = transcript_service
        try:
            yield
        finally:
            if managed_service:
                transcript_service.shutdown()

    app = FastAPI(
        title="Ghost YT Downloader SaaS API",
        description=(
            "API para extraer transcripciones de YouTube como jobs individuales "
            "o por lotes, autenticada mediante X-API-Key. "
            "Los endpoints /v1/* son asíncronos en el sentido de producto: "
            "aceptan trabajo y devuelven estado para polling posterior."
        ),
        version="2.0.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Healthcheck and service metadata."},
            {
                "name": "legacy",
                "description": "Legacy synchronous endpoint kept for local debugging.",
            },
            {
                "name": "transcripts",
                "description": "Single transcript job creation and polling endpoints.",
            },
            {
                "name": "batches",
                "description": "Batch creation and polling endpoints for many videos.",
            },
        ],
    )

    # Configuración de CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Healthcheck",
        description="Returns a simple readiness response for uptime or smoke checks.",
    )
    def healthcheck() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/api/transcript",
        response_model=TranscriptResponse,
        tags=["legacy"],
        summary="Legacy synchronous transcript endpoint",
        description=(
            "Blocks until the transcript is resolved. Useful for local debugging, "
            "but SaaS clients should prefer the /v1/transcripts job flow."
        ),
    )
    def get_transcript(
        video: str = Query(
            ...,
            description="YouTube video ID or full URL.",
            examples=["dQw4w9WgXcQ"],
        ),
        lang: str = Query(
            "es,en",
            description="Comma-separated preferred languages.",
            examples=["es,en"],
        ),
    ) -> dict:
        """Legacy synchronous endpoint kept for local debugging."""
        preferred_languages = [
            lang_code.strip() for lang_code in lang.split(",") if lang_code.strip()
        ]

        try:
            result = download_transcript(video, preferred_languages=preferred_languages)
            return result.to_dict()
        except (TranscriptDownloadError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise HTTPException(
                status_code=500,
                detail="Error interno del servidor",
            ) from exc

    @app.post(
        "/v1/transcripts",
        response_model=TranscriptJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["transcripts"],
        summary="Create one transcript job",
        description=(
            "Creates one transcript job. The response usually returns status=queued. "
            "Clients should then poll GET /v1/transcripts/{transcript_id} until a terminal state."
        ),
    )
    def create_transcript_job(
        payload: TranscriptCreateRequest,
        service: TranscriptSaaSService = service_dependency,
        _: str = api_key_dependency,
    ) -> dict:
        return service.create_transcript_request(payload.video, payload.languages)

    @app.get(
        "/v1/transcripts/{transcript_id}",
        response_model=TranscriptJobResponse,
        tags=["transcripts"],
        summary="Get one transcript job",
        description=(
            "Returns the current status and result of one transcript job. "
            "Terminal states are completed and failed."
        ),
    )
    def get_transcript_job(
        transcript_id: str,
        service: TranscriptSaaSService = service_dependency,
        _: str = api_key_dependency,
    ) -> dict:
        job = service.get_transcript_request(transcript_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Transcript request no encontrado")
        return job

    @app.post(
        "/v1/batches",
        response_model=BatchResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["batches"],
        summary="Create one transcript batch",
        description=(
            "Creates a batch of transcript jobs. Each item is processed independently. "
            "Poll the batch and its items to observe progress and results."
        ),
    )
    def create_batch(
        payload: BatchCreateRequest,
        service: TranscriptSaaSService = service_dependency,
        _: str = api_key_dependency,
    ) -> dict:
        if not payload.videos:
            raise HTTPException(
                status_code=400,
                detail="Debes enviar al menos un video en el lote",
            )
        if len(payload.videos) > service.max_batch_size:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"El lote excede el máximo permitido de "
                    f"{service.max_batch_size} videos"
                ),
            )

        return service.create_batch(payload.videos, payload.languages)

    @app.get(
        "/v1/batches/{batch_id}",
        response_model=BatchResponse,
        tags=["batches"],
        summary="Get batch status",
        description=(
            "Returns aggregate status counters for one batch. "
            "Use it to know whether to keep polling or to fetch per-item results."
        ),
    )
    def get_batch(
        batch_id: str,
        service: TranscriptSaaSService = service_dependency,
        _: str = api_key_dependency,
    ) -> dict:
        batch = service.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="Batch no encontrado")
        return batch

    @app.get(
        "/v1/batches/{batch_id}/items",
        response_model=BatchItemsResponse,
        tags=["batches"],
        summary="List batch items",
        description=(
            "Returns all transcript jobs created for one batch, including completed, "
            "failed, queued, and processing items."
        ),
    )
    def get_batch_items(
        batch_id: str,
        service: TranscriptSaaSService = service_dependency,
        _: str = api_key_dependency,
    ) -> dict:
        batch = service.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="Batch no encontrado")

        return {"batch_id": batch_id, "items": service.get_batch_items(batch_id)}

    return app


app = create_app()
