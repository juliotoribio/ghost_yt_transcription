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
    normalized_languages = tuple(preferred_languages)

    try:
        video_id = extract_video_id(video_url_or_id)
    except ValueError as exc:
        raise TranscriptDownloadError(str(exc)) from exc

    _check_dependencies()
    info = _fetch_video_info(video_id)
    url, lang, source = _select_best_subtitle_url(info, normalized_languages)
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
    """Selecciona la mejor pista json3 considerando idioma base y variantes regionales."""
    subs_manual: dict[str, list[dict[str, Any]]] = info.get("subtitles", {})
    subs_auto: dict[str, list[dict[str, Any]]] = info.get("automatic_captions", {})
    normalized_languages = tuple(preferred_languages)

    for lang in normalized_languages:
        matched_lang, url_to_fetch = _find_matching_subtitle_url(subs_manual, lang)
        if url_to_fetch:
            return url_to_fetch, matched_lang, "yt_dlp_manual"

        matched_lang, url_to_fetch = _find_matching_subtitle_url(subs_auto, lang)
        if url_to_fetch:
            return url_to_fetch, matched_lang, "yt_dlp_auto"

    raise TranscriptDownloadError(
        f"No se encontraron subtítulos para el video "
        f"en los idiomas solicitados {list(normalized_languages)}"
    )


def _download_subtitle_payload(
    url: str, timeout: int, session: Any | None
) -> dict[str, Any]:
    """Realiza la petición HTTP pura para aislar el I/O del parseo."""
    try:
        if session is not None:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()  # type: ignore

        with requests.Session() as req_session:
            resp = req_session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()  # type: ignore
    except Exception as e:
        raise TranscriptDownloadError(
            f"Error descargando el JSON del subtítulo: {e}"
        ) from e


def _get_json3_url(format_list: list[dict[str, Any]]) -> str | None:
    for fmt in format_list:
        if fmt.get("ext") == "json3":
            return fmt.get("url")
    return None


def _find_matching_subtitle_url(
    subtitles: dict[str, list[dict[str, Any]]], preferred_language: str
) -> tuple[str, str | None]:
    for lang_code in _iter_language_matches(subtitles, preferred_language):
        url = _get_json3_url(subtitles[lang_code])
        if url:
            return lang_code, url
    return preferred_language, None


def _iter_language_matches(
    subtitles: dict[str, list[dict[str, Any]]], preferred_language: str
) -> list[str]:
    normalized_preference = _normalize_language_code(preferred_language)
    exact_matches = [
        lang_code
        for lang_code in subtitles
        if _normalize_language_code(lang_code) == normalized_preference
    ]
    if exact_matches:
        return exact_matches

    preferred_base = normalized_preference.split("-", maxsplit=1)[0]
    return [
        lang_code
        for lang_code in subtitles
        if _normalize_language_code(lang_code).split("-", maxsplit=1)[0]
        == preferred_base
    ]


def _normalize_language_code(language_code: str) -> str:
    return language_code.strip().lower().replace("_", "-")


def _parse_json3_transcript(data: dict) -> str:
    """Extrae el texto crudo del formato json3 y lo normaliza a texto corrido."""
    segments = []
    events = data.get("events", [])
    for event in events:
        for seg in event.get("segs", []):
            if "utf8" in seg:
                segments.append(seg["utf8"])
    full_text = "".join(segments)
    return re.sub(r"\s+", " ", full_text).strip()


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
