import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import douyin_login


class ConfigStorageTests(unittest.TestCase):
    def test_save_cookie_writes_only_config_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            cookie_path = Path(temp_dir) / "douyin_cookie.txt"

            with mock.patch.object(douyin_login, "CONFIG_PATH", str(config_path)), mock.patch.object(
                douyin_login,
                "COOKIE_PATH",
                str(cookie_path),
            ):
                douyin_login.save_cookie("sessionid=abc", save_dir="/tmp/downloads")

            self.assertFalse(cookie_path.exists())
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {
                    "cookie": "sessionid=abc",
                    "save_dir": "/tmp/downloads",
                },
            )

    def test_load_saved_cookie_migrates_legacy_cookie_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            cookie_path = Path(temp_dir) / "douyin_cookie.txt"
            cookie_path.write_text("\ufeffsessionid=legacy\n", encoding="utf-8")

            with mock.patch.object(douyin_login, "CONFIG_PATH", str(config_path)), mock.patch.object(
                douyin_login,
                "COOKIE_PATH",
                str(cookie_path),
            ):
                cookie = douyin_login.load_saved_cookie()

            self.assertEqual(cookie, "sessionid=legacy")
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["cookie"], "sessionid=legacy")
            self.assertFalse(cookie_path.exists())
