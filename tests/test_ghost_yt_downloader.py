import unittest

from ghost_yt_downloader import _parse_json3_transcript, extract_video_id

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

    def test_parse_json3_transcript_joins_segments(self) -> None:
        transcript = _parse_json3_transcript(SAMPLE_JSON3)
        self.assertEqual(transcript, "Hola mundo\nSegunda línea")


if __name__ == "__main__":
    unittest.main()
