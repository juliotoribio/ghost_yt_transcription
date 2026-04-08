import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import download_transcript as cli_module
from ghost_yt_downloader import TranscriptDownloadError, TranscriptResult

try:
    from fastapi import HTTPException

    import main
except ModuleNotFoundError:  # pragma: no cover
    HTTPException = None
    main = None


@unittest.skipIf(HTTPException is None, "fastapi no está instalado en este entorno")
class FastAPIInterfaceTests(unittest.TestCase):
    def test_api_returns_transcript_payload(self) -> None:
        result = TranscriptResult(
            video_id="dQw4w9WgXcQ",
            language="es",
            source="yt_dlp_manual",
            text="hola",
        )

        with patch("main.download_transcript", return_value=result) as mocked:
            response = main.get_transcript(
                video="https://youtu.be/dQw4w9WgXcQ", lang="es, en"
            )

        self.assertEqual(response, result.to_dict())
        mocked.assert_called_once_with(
            "https://youtu.be/dQw4w9WgXcQ", preferred_languages=["es", "en"]
        )

    def test_api_maps_transcript_error_to_http_400(self) -> None:
        with patch(
            "main.download_transcript",
            side_effect=TranscriptDownloadError("video inválido"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                main.get_transcript(video="bad", lang="es,en")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "video inválido")

    def test_api_maps_unexpected_error_to_http_500(self) -> None:
        with patch("main.download_transcript", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as ctx:
                main.get_transcript(video="dQw4w9WgXcQ", lang="es,en")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "Error interno del servidor")


class CliInterfaceTests(unittest.TestCase):
    def test_cli_returns_error_code_and_stderr_for_invalid_input(self) -> None:
        stderr = io.StringIO()

        with patch.object(sys, "argv", ["download_transcript.py", "bad"]):
            with redirect_stderr(stderr):
                exit_code = cli_module.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("No se pudo extraer un video ID válido", stderr.getvalue())

    def test_cli_writes_json_output_to_file(self) -> None:
        result = TranscriptResult(
            video_id="dQw4w9WgXcQ",
            language="en",
            source="yt_dlp_auto",
            text="Never gonna give you up",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "transcript.json"
            argv = [
                "download_transcript.py",
                "dQw4w9WgXcQ",
                "--json",
                "--output",
                str(output_path),
            ]

            with patch.object(sys, "argv", argv):
                with patch("download_transcript.download_transcript", return_value=result):
                    exit_code = cli_module.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                result.to_dict(),
            )


if __name__ == "__main__":
    unittest.main()
