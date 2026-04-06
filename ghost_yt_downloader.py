from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import requests
    import yt_dlp
except ImportError:  # pragma: no cover
    requests = None  # type: ignore
    yt_dlp = None  # type: ignore


class TranscriptDownloadError(RuntimeError):
    """Raised when every transcript strategy fails."""


@dataclass
class TranscriptResult:
    video_id: str
    text: str
    source: str
    language: str | None = None
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "language": self.language,
            "source": self.source,
            "text": self.text,
        }


def download_transcript(
    video_url_or_id: str,
    preferred_languages: Iterable[str] = ("es", "en"),
    timeout: int = 20,
    session: Any | None = None,
) -> TranscriptResult:
    """Extrae la transcripción orquestando la metadata, selección, descarga y parseo."""
    _check_dependencies()
    video_id = extract_video_id(video_url_or_id)

    info = _fetch_video_info(video_id)
    url, lang, source = _select_best_subtitle_url(info, preferred_languages)
    raw_json = _download_subtitle_payload(url, timeout, session)

    text = _parse_json3_transcript(raw_json)
    if not text:
        raise TranscriptDownloadError("La transcripción parseada está vacía.")

    return TranscriptResult(
        video_id=video_id,
        text=text,
        source=source,
        language=lang,
        raw_response=raw_json,
    )


def _check_dependencies() -> None:
    if yt_dlp is None or requests is None:
        raise TranscriptDownloadError(
            "Faltan dependencias ('yt-dlp' o 'requests'). "
            "Instálalas con: pip install yt-dlp requests"
        )


def _fetch_video_info(video_id: str) -> dict[str, Any]:
    """Obtiene la metadata dict cruda desde yt_dlp."""
    ydl_opts: Any = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "logger": None,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_id, download=False)  # type: ignore
    except Exception as e:
        raise TranscriptDownloadError(
            f"yt-dlp error extrayendo info del video: {e}"
        ) from e


def _select_best_subtitle_url(
    info: dict[str, Any], preferred_languages: Iterable[str]
) -> tuple[str, str, str]:
    """Applies pure business rules to select the best subtitle source URL."""
    subs_manual: dict[str, list[dict[str, Any]]] = info.get("subtitles", {})
    subs_auto: dict[str, list[dict[str, Any]]] = info.get("automatic_captions", {})

    for lang in preferred_languages:
        # Check manual subtitles first
        if lang in subs_manual:
            url_to_fetch = _get_json3_url(subs_manual[lang])
            if url_to_fetch:
                return url_to_fetch, lang, "yt_dlp_manual"

        # Fallback to automatic captions
        if lang in subs_auto:
            url_to_fetch = _get_json3_url(subs_auto[lang])
            if url_to_fetch:
                return url_to_fetch, lang, "yt_dlp_auto"

    raise TranscriptDownloadError(
        f"No se encontraron subtítulos para el video "
        f"en los idiomas solicitados {list(preferred_languages)}"
    )


def _download_subtitle_payload(
    url: str, timeout: int, session: Any | None
) -> dict[str, Any]:
    """Realiza la petición HTTP pura para aislar el I/O del parseo."""
    try:
        req_session = session or requests.Session()
        resp = req_session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()  # type: ignore
    except Exception as e:
        raise TranscriptDownloadError(
            f"Error descargando el JSON del subtítulo: {e}"
        ) from e


def _get_json3_url(format_list: list[dict]) -> str | None:
    for fmt in format_list:
        if fmt.get("ext") == "json3":
            return fmt.get("url")
    return None


def _parse_json3_transcript(data: dict) -> str:
    """Extrae el texto crudo del formato json3 de YouTube."""
    segments = []
    events = data.get("events", [])
    for event in events:
        for seg in event.get("segs", []):
            if "utf8" in seg:
                segments.append(seg["utf8"])
    return "".join(segments).strip()


def extract_video_id(video_url_or_id: str) -> str:
    candidate = video_url_or_id.strip()
    if re.fullmatch(r"[\w-]{11}", candidate):
        return candidate

    parsed = urlparse(candidate)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")

    if host == "youtu.be" and path:
        return path.split("/")[0]

    if host.endswith("youtube.com"):
        if path == "watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            if video_id:
                return video_id

        path_parts = [part for part in path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
            return path_parts[1]

    raise ValueError(f"No se pudo extraer un video ID válido desde: {video_url_or_id}")
