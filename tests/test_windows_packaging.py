import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT_DIR / "packaging" / "windows" / "verify_bundle.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("windows_verify_bundle", VERIFY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WindowsPackagingTests(unittest.TestCase):
    def test_complete_portable_bundle_satisfies_core_contract(self):
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            self.write(bundle, "抖音视频工具.exe", b"exe")
            self.write(bundle, "runtime/python/python.exe", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "version.json", b'{"version":"1.1.0"}')
            self.write(bundle, "一键更新.bat", b"bat")
            self.write(bundle, "updater.ps1", b"powershell")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-medium/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(verifier.missing_core_paths(bundle), set())

    def test_missing_model_binary_is_reported(self):
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            self.write(bundle, "抖音视频工具.exe", b"exe")
            self.write(bundle, "_internal/python312.dll", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "version.json", b'{"version":"1.1.0"}')
            self.write(bundle, "一键更新.bat", b"bat")
            self.write(bundle, "updater.ps1", b"powershell")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-medium/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(
                verifier.missing_core_paths(bundle),
                {"models/faster-whisper-small/model.bin"},
            )

    def test_missing_updater_script_is_reported(self):
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            self.write(bundle, "抖音视频工具.exe", b"exe")
            self.write(bundle, "_internal/python312.dll", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "version.json", b'{"version":"1.1.0"}')
            self.write(bundle, "一键更新.bat", b"bat")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-medium/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-medium/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(verifier.missing_core_paths(bundle), {"updater.ps1"})

    def test_missing_medium_model_is_reported(self):
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            self.write(bundle, "抖音视频工具.exe", b"exe")
            self.write(bundle, "_internal/python312.dll", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "version.json", b'{"version":"1.2.0"}')
            self.write(bundle, "一键更新.bat", b"bat")
            self.write(bundle, "updater.ps1", b"powershell")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(
                verifier.missing_core_paths(bundle),
                {
                    "models/faster-whisper-medium/config.json",
                    "models/faster-whisper-medium/model.bin",
                    "models/faster-whisper-medium/tokenizer.json",
                },
            )

    def test_one_click_batch_is_ascii_and_calls_ascii_updater_name(self):
        content = (ROOT_DIR / "packaging" / "windows" / "一键更新.bat").read_bytes()

        content.decode("ascii")
        self.assertIn(b"updater.ps1", content)

    def test_model_downloader_can_start_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "packaging/windows/download_model.py", "--help"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    @staticmethod
    def write(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
