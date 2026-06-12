import unittest
from unittest.mock import patch
import json
import os
import tempfile

from douyin_video_parser import DouyinVideoParser
from services.douyin_login import has_login_cookies
from services.download_service import (
    choose_download_url,
    open_video_stream,
    progress_percent,
    serialize_video_info,
    safe_filename,
)


class LoginCookieTests(unittest.TestCase):
    def test_detects_session_cookie_pair(self):
        cookies = [
            {"name": "sessionid", "value": "abc"},
            {"name": "sid_tt", "value": "def"},
        ]

        self.assertTrue(has_login_cookies(cookies))

    def test_rejects_incomplete_cookie(self):
        cookies = [{"name": "sessionid", "value": "abc"}]

        self.assertFalse(has_login_cookies(cookies))


class DownloadHelperTests(unittest.TestCase):
    def test_choose_download_url_prefers_requested_quality(self):
        info = {
            "qualities": [
                {"ratio": "1080p", "bit_rate": 2000000, "url": "https://example.com/1080.mp4"},
                {"ratio": "720p", "bit_rate": 1000000, "url": "https://example.com/720-low.mp4"},
                {"ratio": "720p", "bit_rate": 1500000, "url": "https://example.com/720-high.mp4"},
            ],
            "nwm_url": "https://example.com/fallback.mp4",
        }

        self.assertEqual(
            choose_download_url(info, quality="720p"),
            "https://example.com/720-high.mp4",
        )

    def test_safe_filename_removes_invalid_path_chars(self):
        self.assertEqual(safe_filename('a/b:c*?"<>|', "fallback"), "a_b_c______")

    def test_progress_percent_clamps_to_complete(self):
        self.assertEqual(progress_percent(120, 100), 100)
        self.assertEqual(progress_percent(25, 100), 25)
        self.assertEqual(progress_percent(25, 0), 0)

    def test_serialize_video_info_deduplicates_quality_ratios_and_omits_urls(self):
        info = {
            "aweme_id": "123",
            "desc": "demo",
            "author_nickname": "author",
            "cover_url": "https://example.com/cover.jpg",
            "content_type": "video",
            "qualities": [
                {
                    "ratio": "1080p",
                    "bit_rate": 2000000,
                    "file_size": 12000000,
                    "fps": 60,
                    "quality_label": "1080p (2000Kbps)",
                    "url": "https://example.com/video.mp4",
                },
                {
                    "ratio": "2K",
                    "bit_rate": 1800000,
                    "file_size": 26000000,
                    "fps": 120,
                    "quality_label": "2K (1800Kbps)",
                    "url": "https://example.com/video-2k.mp4",
                },
                {
                    "ratio": "1080p",
                    "bit_rate": 1200000,
                    "file_size": 8000000,
                    "quality_label": "1080p (1200Kbps)",
                    "url": "https://example.com/video-low.mp4",
                },
                {
                    "ratio": "720p",
                    "bit_rate": 1000000,
                    "quality_label": "720p (1000Kbps)",
                    "url": "https://example.com/video-720.mp4",
                }
            ],
        }

        result = serialize_video_info(info)

        self.assertEqual(result["aweme_id"], "123")
        self.assertEqual(result["qualities"][0]["ratio"], "2K")
        self.assertEqual(result["qualities"][0]["file_size"], 26000000)
        self.assertEqual(result["qualities"][0]["fps"], 120)
        self.assertEqual(result["qualities"][1]["ratio"], "1080p")
        self.assertEqual(result["qualities"][1]["bit_rate"], 2000000)
        self.assertEqual(result["qualities"][1]["file_size"], 12000000)
        self.assertEqual(result["qualities"][1]["fps"], 60)
        self.assertEqual([item["ratio"] for item in result["qualities"]], ["2K", "1080p", "720p"])
        self.assertNotIn("url", result["qualities"][1])

    def test_open_video_stream_preserves_partial_content_length(self):
        class FakeParser:
            def set_cookie(self, cookie):
                self.cookie = cookie

            def parse_video(self, share_url):
                return {
                    "content_type": "video",
                    "qualities": [{"ratio": "1080p", "bit_rate": 2000000, "url": "https://example.com/video.mp4"}],
                }

        class FakeResponse:
            status_code = 206
            headers = {
                "content-length": "1024",
                "content-range": "bytes 0-1023/2048",
                "accept-ranges": "bytes",
            }

            def __init__(self):
                self.closed = False

            def iter_content(self, chunk_size):
                yield b"video"

            def close(self):
                self.closed = True

        fake_response = FakeResponse()
        with (
            patch("services.download_service.DouyinVideoParser", FakeParser),
            patch("services.download_service.requests.get", return_value=fake_response) as request_get,
        ):
            stream, status_code, headers = open_video_stream(
                "https://v.douyin.com/demo/",
                cookie="sessionid=abc",
                quality="1080p",
                range_header="bytes=0-1023",
            )

        self.assertEqual(status_code, 206)
        self.assertEqual(headers["content-length"], "1024")
        self.assertEqual(headers["content-range"], "bytes 0-1023/2048")
        self.assertEqual(request_get.call_args.kwargs["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(list(stream), [b"video"])
        self.assertTrue(fake_response.closed)

    def test_extract_video_qualities_writes_debug_log(self):
        data = {
            "aweme_detail": {
                "aweme_id": "7420000000000000000",
                "desc": "demo",
                "video": {
                    "play_addr": {
                        "uri": "fallback-uri",
                        "url_list": ["https://example.com/fallback.mp4?token=secret"],
                    },
                    "bit_rate": [
                        {
                            "bit_rate": 5774000,
                            "gear_name": "adapt_lowest_4_1",
                            "quality_type": 4,
                            "FPS": 120,
                            "play_addr": {
                                "uri": "quality-uri",
                                "data_size": 17515397,
                                "url_list": ["https://example.com/video.mp4?token=secret&ratio=1080p"],
                                "width": 2160,
                                "height": 3840,
                            },
                        }
                    ],
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "quality_debug.jsonl")
            with patch.dict(os.environ, {"DOUYIN_QUALITY_LOG_PATH": log_path}):
                qualities = DouyinVideoParser.extract_video_qualities(data)

            with open(log_path, "r", encoding="utf-8") as file:
                payload = json.loads(file.readline())

        self.assertEqual(qualities[0]["gear_name"], "adapt_lowest_4_1")
        self.assertEqual(payload["aweme_id"], "7420000000000000000")
        self.assertEqual(payload["raw_bit_rate"][0]["gear_name"], "adapt_lowest_4_1")
        self.assertEqual(payload["raw_bit_rate"][0]["play_addr"]["width"], 2160)
        self.assertEqual(payload["extracted_qualities"][0]["ratio"], "4K")
        self.assertEqual(payload["extracted_qualities"][0]["file_size"], 17515397)
        self.assertEqual(payload["extracted_qualities"][0]["fps"], 120)
        self.assertNotIn("token=secret", json.dumps(payload))

    def test_extract_video_qualities_prefers_definition_and_dimensions_over_bitrate(self):
        data = {
            "aweme_detail": {
                "aweme_id": "7566016770223787322",
                "video": {
                    "bit_rate": [
                        {
                            "bit_rate": 5774227,
                            "gear_name": "adapt_lowest_4_1",
                            "quality_type": 72,
                            "FPS": 120,
                            "video_extra": json.dumps({"definition": "4k", "quality": "adapt_lowest"}),
                            "play_addr": {
                                "url_key": "v_bytevc1_4k_5774227",
                                "url_list": ["https://example.com/4k.mp4"],
                                "data_size": 17515397,
                                "width": 2160,
                                "height": 3840,
                            },
                        },
                        {
                            "bit_rate": 3747906,
                            "gear_name": "adapt_lowest_1440_1",
                            "quality_type": 7,
                            "FPS": 60,
                            "video_extra": json.dumps({"definition": "1440p", "quality": "adapt_lowest"}),
                            "play_addr": {
                                "url_key": "v_bytevc1_1440p_3747906",
                                "url_list": ["https://example.com/1440.mp4"],
                                "data_size": 11368110,
                                "width": 1440,
                                "height": 2560,
                            },
                        },
                        {
                            "bit_rate": 2909509,
                            "gear_name": "normal_720_0",
                            "quality_type": 10,
                            "video_extra": json.dumps({"definition": "720p", "quality": "normal"}),
                            "play_addr": {
                                "url_key": "v_h264_720p_2909509",
                                "url_list": ["https://example.com/720.mp4"],
                                "width": 720,
                                "height": 1280,
                            },
                        },
                    ],
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "quality_debug.jsonl")
            with patch.dict(os.environ, {"DOUYIN_QUALITY_LOG_PATH": log_path}):
                qualities = DouyinVideoParser.extract_video_qualities(data)

        self.assertEqual([quality["ratio"] for quality in qualities], ["4K", "2K", "720p"])
        self.assertEqual(qualities[0]["quality_label"], "4K (5774Kbps)")
        self.assertEqual(qualities[0]["file_size"], 17515397)
        self.assertEqual(qualities[0]["fps"], 120)
        self.assertEqual(qualities[1]["quality_label"], "2K (3747Kbps)")
        self.assertEqual(qualities[1]["file_size"], 11368110)
        self.assertEqual(qualities[1]["fps"], 60)


if __name__ == "__main__":
    unittest.main()
