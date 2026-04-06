"""FastAPI service to download YouTube transcripts."""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ghost_yt_downloader import TranscriptDownloadError, download_transcript

app = FastAPI(
    title="Ghost YT Downloader API",
    description="API para extraer transcripciones limpias desde YouTube bypass bots.",
    version="1.0.0",
)


class TranscriptResponse(BaseModel):
    video_id: str
    language: str | None
    source: str
    text: str


@app.get("/api/transcript", response_model=TranscriptResponse)
def get_transcript(
    video: str = Query(..., description="ID o URL completa del video de YouTube."),
    lang: str = Query(
        "es,en", description="Idiomas preferidos separados por coma (ej: 'es,en')."
    ),
) -> dict:
    """Extrae la transcripción de un video específico."""
    preferred_languages = [
        lang_code.strip() for lang_code in lang.split(",") if lang_code.strip()
    ]

    try:
        result = download_transcript(video, preferred_languages=preferred_languages)
        return result.to_dict()
    except TranscriptDownloadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor") from e
