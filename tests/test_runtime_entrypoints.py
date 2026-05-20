import importlib.util
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeEntrypointTests(unittest.TestCase):
    def test_cross_platform_start_files_exist(self):
        self.assertTrue((ROOT_DIR / "start.py").exists())
        self.assertTrue((ROOT_DIR / "start.bat").exists())
        self.assertTrue((ROOT_DIR / "server_runtime.py").exists())

    def test_start_py_resolves_platform_venv_python(self):
        start = load_module("start_module", ROOT_DIR / "start.py")

        self.assertEqual(start.venv_python_path(ROOT_DIR, "posix"), ROOT_DIR / ".venv" / "bin" / "python")
        self.assertEqual(start.venv_python_path(ROOT_DIR, "nt"), ROOT_DIR / ".venv" / "Scripts" / "python.exe")

    def test_server_runtime_builds_health_url(self):
        runtime = load_module("server_runtime_module", ROOT_DIR / "server_runtime.py")

        self.assertEqual(
            runtime.build_service_url("127.0.0.1", 8787, "/health"),
            "http://127.0.0.1:8787/health",
        )
