import importlib.util
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
            self.write(bundle, "_internal/python312.dll", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/model.bin", b"model")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(verifier.missing_core_paths(bundle), set())

    def test_missing_model_binary_is_reported(self):
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            self.write(bundle, "抖音视频工具.exe", b"exe")
            self.write(bundle, "_internal/python312.dll", b"python")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "models/faster-whisper-small/config.json", b"{}")
            self.write(bundle, "models/faster-whisper-small/tokenizer.json", b"{}")
            self.write(bundle, "browsers/chromium/chrome.exe", b"browser")

            self.assertEqual(
                verifier.missing_core_paths(bundle),
                {"models/faster-whisper-small/model.bin"},
            )

    @staticmethod
    def write(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
