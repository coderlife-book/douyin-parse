import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import runtime_paths


class RuntimePathTests(unittest.TestCase):
    def test_environment_root_controls_writable_and_bundled_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {"DOUYIN_PARSE_ROOT": temp_dir},
        ):
            root = Path(temp_dir).resolve()

            self.assertEqual(runtime_paths.portable_root(), root)
            self.assertEqual(runtime_paths.config_path(), root / "config.json")
            self.assertEqual(runtime_paths.downloads_path(), root / "downloads")
            self.assertEqual(runtime_paths.transcripts_path(), root / "data" / "transcripts")
            self.assertEqual(
                runtime_paths.model_path(),
                root / "models" / "faster-whisper-small",
            )
            self.assertEqual(runtime_paths.browser_path(), root / "browsers")
            self.assertEqual(runtime_paths.web_index_path(), root / "web" / "index.html")

    def test_frozen_root_is_executable_parent(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            sys,
            "frozen",
            True,
            create=True,
        ), mock.patch.object(
            sys,
            "executable",
            "/portable/抖音视频工具.exe",
        ):
            self.assertEqual(runtime_paths.portable_root(), Path("/portable"))


if __name__ == "__main__":
    unittest.main()
