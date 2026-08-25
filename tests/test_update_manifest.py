import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "packaging" / "update_manifest.py"
PACKAGE_PATH = ROOT_DIR / "packaging" / "windows" / "build_update_package.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class UpdateManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.manifest_module = load_module("update_manifest_module", MANIFEST_PATH)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manifest_hashes_core_files_and_excludes_portable_data(self):
        self.write("抖音视频工具.exe", b"exe")
        self.write("web/index.html", b"html")
        self.write("config.json", b"cookie")
        self.write("douyin_cookie.txt", b"legacy-cookie")
        self.write("data/transcripts/a/manifest.json", b"private")
        self.write("downloads/video.mp4", b"video")
        self.write("models/faster-whisper-small/model.bin", b"model")
        self.write("browsers/chromium/chrome.exe", b"browser")
        self.write("一键更新.bat", b"bat")
        self.write("updater.ps1", b"powershell")
        self.write("unexpected.bin", b"must-not-ship")

        manifest = self.manifest_module.build_manifest(self.root, "1.1.1", "1.1.0")

        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            ["web/index.html", "抖音视频工具.exe"],
        )
        self.assertEqual(manifest["protocol"], 1)
        self.assertEqual(manifest["files"][1]["size"], 3)
        self.assertEqual(
            manifest["files"][1]["sha256"],
            hashlib.sha256(b"exe").hexdigest(),
        )

    def test_relative_path_rejects_parent_absolute_and_windows_drive_escape(self):
        for value in ("../config.json", "..\\config.json", "/config.json", "C:/config.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.manifest_module.validate_relative_path(value)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


class UpdatePackageTests(unittest.TestCase):
    def test_update_zip_contains_manifest_and_only_hashed_core_payload(self):
        package_module = load_module("build_update_package_module", PACKAGE_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = root / "bundle"
            output = root / "更新包-v1.1.1.zip"
            self.write(bundle, "抖音视频工具.exe", b"new-exe")
            self.write(bundle, "_internal/runtime.dll", b"runtime")
            self.write(bundle, "web/index.html", b"html")
            self.write(bundle, "version.json", b'{"version":"1.1.1"}')
            self.write(bundle, "models/faster-whisper-small/model.bin", b"model")
            self.write(bundle, "data/transcripts/one/manifest.json", b"private")
            self.write(bundle, "douyin_cookie.txt", b"legacy-cookie")
            self.write(bundle, "unexpected.bin", b"must-not-ship")

            package_module.create_update_package(
                bundle,
                output,
                version="1.1.1",
                minimum_version="1.1.0",
            )

            with zipfile.ZipFile(output) as archive:
                names = sorted(archive.namelist())
                manifest = json.loads(archive.read("update-manifest.json"))

        self.assertEqual(
            names,
            [
                "payload/_internal/runtime.dll",
                "payload/version.json",
                "payload/web/index.html",
                "payload/抖音视频工具.exe",
                "update-manifest.json",
            ],
        )
        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            ["_internal/runtime.dll", "version.json", "web/index.html", "抖音视频工具.exe"],
        )

    @staticmethod
    def write(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
