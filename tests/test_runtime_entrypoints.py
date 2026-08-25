import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


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

    def test_background_server_passes_asgi_app_object_to_uvicorn(self):
        runtime = load_module("server_runtime_app_module", ROOT_DIR / "server_runtime.py")
        asgi_app = object()

        class FakeServer:
            should_exit = False

            def __init__(self, config):
                self.config = config

            def run(self):
                return None

        fake_uvicorn = types.SimpleNamespace(
            Config=mock.Mock(return_value=object()),
            Server=FakeServer,
        )
        with mock.patch.dict(
            sys.modules,
            {
                "api_server": types.SimpleNamespace(app=asgi_app),
                "uvicorn": fake_uvicorn,
            },
        ), mock.patch.object(runtime, "is_service_ready", side_effect=[False, True]):
            handle = runtime.start_background_server(timeout=0.1)

        fake_uvicorn.Config.assert_called_once_with(
            asgi_app,
            host="127.0.0.1",
            port=8787,
            log_level="info",
        )
        runtime.stop_background_server(handle)
