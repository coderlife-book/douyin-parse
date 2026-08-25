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
            self.assertEqual(
                runtime_paths.portable_chromium_path(),
                root / "browsers" / "chromium" / "chrome.exe",
            )
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

    def test_available_asr_models_only_returns_complete_supported_models(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {"DOUYIN_PARSE_ROOT": temp_dir},
        ):
            root = Path(temp_dir)
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                path = root / "models" / "faster-whisper-medium" / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ready", encoding="utf-8")
            incomplete = root / "models" / "faster-whisper-small"
            incomplete.mkdir(parents=True)
            (incomplete / "config.json").write_text("{}", encoding="utf-8")
            unsupported = root / "models" / "faster-whisper-large-v3"
            unsupported.mkdir(parents=True)
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                (unsupported / filename).write_text("ready", encoding="utf-8")

            models = runtime_paths.available_asr_models()

        self.assertEqual(
            models,
            [
                {
                    "id": "medium",
                    "label": "Medium",
                    "description": "效果更好，识别速度较慢",
                    "is_default": False,
                }
            ],
        )

    def test_asr_model_path_rejects_unsupported_model(self):
        with self.assertRaisesRegex(ValueError, "不支持的 ASR 模型"):
            runtime_paths.asr_model_path("large-v3")


if __name__ == "__main__":
    unittest.main()
