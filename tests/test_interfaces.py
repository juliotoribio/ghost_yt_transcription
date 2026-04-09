import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import download_transcript as cli_module
from ghost_yt_downloader import TranscriptResult
from saas_service import ServiceConfig, TranscriptSaaSService
from saas_store import SQLiteStore

try:
    from fastapi.testclient import TestClient

    import main
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None
    main = None


def build_test_service(db_path: str) -> TranscriptSaaSService:
    store = SQLiteStore(db_path)
    store.init_db()
    service = TranscriptSaaSService(
        store,
        ServiceConfig(auto_process=False, max_batch_size=2),
    )
    service.ensure_default_api_key("test-key")
    return service


@unittest.skipIf(TestClient is None, "fastapi/httpx no está instalado en este entorno")
class SaaSApiTests(unittest.TestCase):
    def test_openapi_exposes_llm_friendly_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                response = client.get("/openapi.json")

            self.assertEqual(response.status_code, 200)
            spec = response.json()
            self.assertEqual(spec["info"]["title"], "Ghost YT Downloader SaaS API")
            self.assertIn("/v1/transcripts", spec["paths"])
            self.assertIn("summary", spec["paths"]["/v1/transcripts"]["post"])
            self.assertIn("description", spec["paths"]["/v1/batches"]["post"])

    def test_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                response = client.post(
                    "/v1/transcripts",
                    json={"video": "dQw4w9WgXcQ", "languages": ["es", "en"]},
                )

            self.assertEqual(response.status_code, 401)

    def test_creates_single_job_and_processes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                response = client.post(
                    "/v1/transcripts",
                    headers={"X-API-Key": "test-key"},
                    json={"video": "dQw4w9WgXcQ", "languages": ["es", "en"]},
                )
                self.assertEqual(response.status_code, 202)
                payload = response.json()
                self.assertEqual(payload["status"], "queued")

                with patch(
                    "saas_service.download_transcript",
                    return_value=TranscriptResult(
                        video_id="dQw4w9WgXcQ",
                        language="es",
                        source="yt_dlp_manual",
                        text="hola mundo",
                    ),
                ):
                    service.process_transcript_request(payload["id"])

                result = client.get(
                    f'/v1/transcripts/{payload["id"]}',
                    headers={"X-API-Key": "test-key"},
                )

            self.assertEqual(result.status_code, 200)
            body = result.json()
            self.assertEqual(body["status"], "completed")
            self.assertEqual(body["text"], "hola mundo")
            self.assertFalse(body["cached"])

    def test_uses_cache_for_repeated_single_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                first = client.post(
                    "/v1/transcripts",
                    headers={"X-API-Key": "test-key"},
                    json={"video": "dQw4w9WgXcQ", "languages": ["es", "en"]},
                ).json()

                with patch(
                    "saas_service.download_transcript",
                    return_value=TranscriptResult(
                        video_id="dQw4w9WgXcQ",
                        language="es",
                        source="yt_dlp_manual",
                        text="hola mundo",
                    ),
                ):
                    service.process_transcript_request(first["id"])

                second = client.post(
                    "/v1/transcripts",
                    headers={"X-API-Key": "test-key"},
                    json={"video": "https://youtu.be/dQw4w9WgXcQ", "languages": ["es", "en"]},
                )

            self.assertEqual(second.status_code, 202)
            payload = second.json()
            self.assertEqual(payload["status"], "completed")
            self.assertTrue(payload["cached"])
            self.assertEqual(payload["text"], "hola mundo")

    def test_batch_tracks_items_and_final_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                created = client.post(
                    "/v1/batches",
                    headers={"X-API-Key": "test-key"},
                    json={"videos": ["bad", "dQw4w9WgXcQ"], "languages": ["es", "en"]},
                )
                self.assertEqual(created.status_code, 202)
                batch = created.json()
                self.assertEqual(batch["status"], "processing")

                items_response = client.get(
                    f'/v1/batches/{batch["id"]}/items',
                    headers={"X-API-Key": "test-key"},
                )
                items = items_response.json()["items"]
                queued_job_id = next(item["id"] for item in items if item["status"] == "queued")

                with patch(
                    "saas_service.download_transcript",
                    return_value=TranscriptResult(
                        video_id="dQw4w9WgXcQ",
                        language="es",
                        source="yt_dlp_auto",
                        text="texto batch",
                    ),
                ):
                    service.process_transcript_request(queued_job_id)

                final_batch = client.get(
                    f'/v1/batches/{batch["id"]}',
                    headers={"X-API-Key": "test-key"},
                )

            self.assertEqual(final_batch.status_code, 200)
            payload = final_batch.json()
            self.assertEqual(payload["status"], "completed_with_errors")
            self.assertEqual(payload["completed_items"], 1)
            self.assertEqual(payload["failed_items"], 1)

    def test_batch_rejects_when_exceeding_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = build_test_service(str(Path(tmpdir) / "test.db"))
            app = main.create_app(service)

            with TestClient(app) as client:
                response = client.post(
                    "/v1/batches",
                    headers={"X-API-Key": "test-key"},
                    json={
                        "videos": ["a", "b", "c"],
                        "languages": ["es", "en"],
                    },
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("máximo permitido", response.json()["detail"])


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
