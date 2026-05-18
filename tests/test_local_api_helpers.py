import unittest

from services.douyin_login import has_login_cookies
from services.download_service import choose_download_url, progress_percent, serialize_video_info, safe_filename


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
                    "quality_label": "1080p (2000Kbps)",
                    "url": "https://example.com/video.mp4",
                },
                {
                    "ratio": "1080p",
                    "bit_rate": 1200000,
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
        self.assertEqual(result["qualities"][0]["ratio"], "1080p")
        self.assertEqual(result["qualities"][0]["bit_rate"], 2000000)
        self.assertEqual([item["ratio"] for item in result["qualities"]], ["1080p", "720p"])
        self.assertNotIn("url", result["qualities"][0])


if __name__ == "__main__":
    unittest.main()
