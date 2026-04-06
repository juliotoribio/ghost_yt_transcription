from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_yt_downloader import TranscriptDownloadError, download_transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Descarga transcripciones de YouTube usando InnerTube y fallback.",
    )
    parser.add_argument("video", help="URL o video ID de YouTube.")
    parser.add_argument(
        "--lang",
        action="append",
        dest="languages",
        default=None,
        help="Idioma preferido para el fallback. Puede repetirse.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Archivo de salida. Si no se indica, imprime en stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Devuelve metadata y texto como JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    languages = tuple(args.languages or ("es", "en"))

    try:
        result = download_transcript(args.video, preferred_languages=languages)
    except TranscriptDownloadError as exc:
        print(f"Error: {exc}")
        return 1

    if args.as_json:
        content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    else:
        content = result.text

    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
