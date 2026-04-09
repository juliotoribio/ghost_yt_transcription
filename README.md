# Ghost YT Downloader SaaS API

Ghost YT Downloader ahora funciona como un MVP SaaS local:

- extracción individual de transcripciones
- procesamiento por lotes
- autenticación por `API key`
- persistencia local con SQLite
- cache simple por `video_id + idiomas`

La lógica de descarga sigue viviendo en `ghost_yt_downloader.py`, pero el servicio HTTP añade estado, jobs, batches y control de acceso.

Documentación para agentes/LLMs:

- `llms.txt`
- `docs/llm-api-reference.md`
- `http://127.0.0.1:8000/openapi.json`

## Arquitectura

- [ghost_yt_downloader.py](/Users/user/Documents/DEV/ghost_yt_transcription/ghost_yt_downloader.py): núcleo de extracción y parseo de una transcripción.
- [saas_store.py](/Users/user/Documents/DEV/ghost_yt_transcription/saas_store.py): persistencia SQLite de keys, jobs y batches.
- [saas_service.py](/Users/user/Documents/DEV/ghost_yt_transcription/saas_service.py): reglas de negocio, cache y procesamiento en background.
- [main.py](/Users/user/Documents/DEV/ghost_yt_transcription/main.py): API FastAPI con endpoints single y batch.
- [manage_api_keys.py](/Users/user/Documents/DEV/ghost_yt_transcription/manage_api_keys.py): CLI para crear, listar y desactivar API keys.

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Configuración

Variables opcionales:

- `GHOST_DB_PATH`: ruta del archivo SQLite. Default: `ghost_saas.db`
- `GHOST_API_KEY`: API key inicial creada al arrancar. Default: `ghost-dev-key`
- `GHOST_WORKER_COUNT`: concurrencia local para jobs en background. Default: `4`
- `GHOST_MAX_BATCH_SIZE`: máximo de videos por lote. Default: `200`

Ejemplo:

```bash
export GHOST_API_KEY="sk_dev_local_123"
export GHOST_WORKER_COUNT="6"
export GHOST_MAX_BATCH_SIZE="200"
```

## Emitir API Keys

Crear una nueva key:

```bash
python3 manage_api_keys.py create "cliente-acme"
```

Crear una key con valor explícito:

```bash
python3 manage_api_keys.py create "cliente-acme" --key "sk_live_acme_001"
```

Listar keys:

```bash
python3 manage_api_keys.py list
```

Desactivar una key:

```bash
python3 manage_api_keys.py deactivate "sk_live_acme_001"
```

## Levantar la API

```bash
uvicorn main:app --reload
```

Swagger:

`http://127.0.0.1:8000/docs`

Healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

## Autenticación

Los endpoints SaaS usan el header `X-API-Key`.

```bash
-H "X-API-Key: ghost-dev-key"
```

## Endpoint Single

Crear un job individual:

```bash
curl -X POST http://127.0.0.1:8000/v1/transcripts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ghost-dev-key" \
  -d '{
    "video": "dQw4w9WgXcQ",
    "languages": ["es", "en"]
  }'
```

Respuesta típica:

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

Consultar estado y resultado:

```bash
curl http://127.0.0.1:8000/v1/transcripts/tr_123abc \
  -H "X-API-Key: ghost-dev-key"
```

Estados posibles:

- `queued`
- `processing`
- `completed`
- `failed`

## Endpoint Batch

Crear un lote:

```bash
curl -X POST http://127.0.0.1:8000/v1/batches \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ghost-dev-key" \
  -d '{
    "videos": [
      "dQw4w9WgXcQ",
      "https://www.youtube.com/watch?v=5X26m52lMwU"
    ],
    "languages": ["es", "en"]
  }'
```

Respuesta:

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

Consultar el lote:

```bash
curl http://127.0.0.1:8000/v1/batches/bat_123abc \
  -H "X-API-Key: ghost-dev-key"
```

Consultar items del lote:

```bash
curl http://127.0.0.1:8000/v1/batches/bat_123abc/items \
  -H "X-API-Key: ghost-dev-key"
```

Estados posibles del batch:

- `processing`
- `completed`
- `failed`
- `completed_with_errors`

## Endpoint Legacy

Se mantiene el endpoint síncrono original para debugging local:

```bash
curl "http://127.0.0.1:8000/api/transcript?video=dQw4w9WgXcQ&lang=es,en"
```

No es el endpoint recomendado para el flujo SaaS.

## Comportamiento del cache

Si una transcripción para el mismo `video_id` y la misma lista de idiomas ya fue completada, una nueva petición single reutiliza el resultado y se marca como:

```json
{
  "status": "completed",
  "cached": true
}
```

## Tests y calidad

```bash
venv/bin/python -m unittest discover tests/
venv/bin/ruff check .
venv/bin/mypy
```
