import unittest

from ghost_yt_downloader import (
    TranscriptDownloadError,
    _parse_json3_transcript,
    _select_best_subtitle_url,
    download_transcript,
    extract_video_id,
)

SAMPLE_JSON3 = {
    "events": [
        {"segs": [{"utf8": "Hola "}, {"utf8": "mundo"}]},
        {"segs": [{"utf8": "\nSegunda línea"}]},
    ]
}


class GhostYTDownloaderTests(unittest.TestCase):
    def test_extract_video_id_accepts_url_and_id(self) -> None:
        self.assertEqual(extract_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=5"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_extract_video_id_rejects_invalid_input(self) -> None:
        with self.assertRaises(ValueError):
            extract_video_id("bad")

    def test_parse_json3_transcript_joins_segments(self) -> None:
        transcript = _parse_json3_transcript(SAMPLE_JSON3)
        self.assertEqual(transcript, "Hola mundo Segunda línea")

    def test_select_best_subtitle_url_prefers_manual_before_auto(self) -> None:
        info = {
            "subtitles": {"en": [{"ext": "json3", "url": "manual-url"}]},
            "automatic_captions": {"en": [{"ext": "json3", "url": "auto-url"}]},
        }

        url, lang, source = _select_best_subtitle_url(info, ("en",))

        self.assertEqual(url, "manual-url")
        self.assertEqual(lang, "en")
        self.assertEqual(source, "yt_dlp_manual")

    def test_select_best_subtitle_url_matches_regional_language_variant(self) -> None:
        info = {
            "subtitles": {
                "es-419": [{"ext": "json3", "url": "regional-url"}],
            },
            "automatic_captions": {},
        }

        url, lang, source = _select_best_subtitle_url(info, ("es",))

        self.assertEqual(url, "regional-url")
        self.assertEqual(lang, "es-419")
        self.assertEqual(source, "yt_dlp_manual")

    def test_download_transcript_wraps_invalid_video_id(self) -> None:
        with self.assertRaises(TranscriptDownloadError) as ctx:
            download_transcript("bad")

        self.assertIn("No se pudo extraer un video ID válido", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
