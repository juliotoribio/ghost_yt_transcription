# LLM API Reference

This document is optimized for machine consumption and agent planning.

## Purpose

Expose a local SaaS-style API that accepts one or many YouTube videos, creates transcript jobs, processes them in background workers, and lets the client poll for results.

## Base behavior

- Authentication is required for all SaaS endpoints.
- Use the `X-API-Key` header.
- `POST` endpoints usually return `202 Accepted`.
- A `202` response means "job accepted", not "job completed".
- Results should be read later via `GET`.

## Endpoint Map

### `GET /health`

Use for readiness checks.

Response:

```json
{
  "status": "ok"
}
```

### `POST /v1/transcripts`

Create one transcript job.

Request body:

```json
{
  "video": "dQw4w9WgXcQ",
  "languages": ["es", "en"]
}
```

Response shape:

```json
{
  "id": "tr_123abc",
  "batch_id": null,
  "status": "queued",
  "video_input": "dQw4w9WgXcQ",
  "video_id": "dQw4w9WgXcQ",
  "languages": ["es", "en"],
  "language": null,
  "source": null,
  "text": null,
  "error_message": null,
  "cached": false,
  "created_at": "2026-04-08T20:00:00+00:00",
  "updated_at": "2026-04-08T20:00:00+00:00"
}
```

Terminal success example:

```json
{
  "id": "tr_123abc",
  "batch_id": null,
  "status": "completed",
  "video_input": "dQw4w9WgXcQ",
  "video_id": "dQw4w9WgXcQ",
  "languages": ["es", "en"],
  "language": "es",
  "source": "yt_dlp_auto",
  "text": "texto corrido aqui",
  "error_message": null,
  "cached": false,
  "created_at": "2026-04-08T20:00:00+00:00",
  "updated_at": "2026-04-08T20:00:02+00:00"
}
```

Terminal failure example:

```json
{
  "id": "tr_123abc",
  "batch_id": null,
  "status": "failed",
  "video_input": "bad",
  "video_id": null,
  "languages": ["es", "en"],
  "language": null,
  "source": null,
  "text": null,
  "error_message": "No se pudo extraer un video ID válido desde: bad",
  "cached": false,
  "created_at": "2026-04-08T20:00:00+00:00",
  "updated_at": "2026-04-08T20:00:00+00:00"
}
```

### `GET /v1/transcripts/{transcript_id}`

Poll one transcript job until status is `completed` or `failed`.

### `POST /v1/batches`

Create a batch of transcript jobs.

Request body:

```json
{
  "videos": [
    "dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=5X26m52lMwU"
  ],
  "languages": ["es", "en"]
}
```

Response shape:

```json
{
  "id": "bat_123abc",
  "status": "processing",
  "languages": ["es", "en"],
  "total_items": 2,
  "completed_items": 0,
  "failed_items": 0,
  "processing_items": 2,
  "created_at": "2026-04-08T20:00:00+00:00",
  "updated_at": "2026-04-08T20:00:00+00:00"
}
```

### `GET /v1/batches/{batch_id}`

Poll aggregate batch status.

### `GET /v1/batches/{batch_id}/items`

Read all transcript jobs created for the batch.

Response shape:

```json
{
  "batch_id": "bat_123abc",
  "items": [
    {
      "id": "tr_1",
      "batch_id": "bat_123abc",
      "status": "completed",
      "video_input": "dQw4w9WgXcQ",
      "video_id": "dQw4w9WgXcQ",
      "languages": ["es", "en"],
      "language": "es",
      "source": "yt_dlp_auto",
      "text": "texto corrido aqui",
      "error_message": null,
      "cached": false,
      "created_at": "2026-04-08T20:00:00+00:00",
      "updated_at": "2026-04-08T20:00:02+00:00"
    }
  ]
}
```

### `GET /api/transcript`

Legacy synchronous endpoint for local debugging only.

Use only when you explicitly want direct blocking behavior and do not need job tracking.

## Authentication

Header:

```http
X-API-Key: ghost-dev-key
```

CLI management:

```bash
python3 manage_api_keys.py create "client-name"
python3 manage_api_keys.py list
python3 manage_api_keys.py deactivate "key-value"
```

## Status semantics

Transcript job:

- `queued`: accepted, waiting for background processing
- `processing`: worker is currently resolving the transcript
- `completed`: transcript is available
- `failed`: transcript could not be resolved

Batch:

- `processing`: at least one child job is still queued or processing
- `completed`: all child jobs completed successfully
- `failed`: all child jobs failed
- `completed_with_errors`: mix of completed and failed items

## Cache semantics

- Cache key = `video_id + ordered languages list`
- A repeated single request may immediately return:
  - `status = completed`
  - `cached = true`

## Constraints

- Default max batch size is `200`
- Controlled with `GHOST_MAX_BATCH_SIZE`
- Default worker count is `4`
- Controlled with `GHOST_WORKER_COUNT`

## Recommended client strategy

For one video:

1. `POST /v1/transcripts`
2. store `id`
3. poll `GET /v1/transcripts/{id}`
4. stop on `completed` or `failed`

For many videos:

1. `POST /v1/batches`
2. store `batch_id`
3. poll `GET /v1/batches/{batch_id}`
4. once terminal, read `GET /v1/batches/{batch_id}/items`

## Error handling

- `401`: missing or invalid API key
- `404`: transcript job or batch not found
- `400`: invalid request payload or batch too large
- `500`: unexpected internal error on legacy sync endpoint

## Files to inspect for implementation details

- `main.py`
- `saas_service.py`
- `saas_store.py`
- `ghost_yt_downloader.py`
