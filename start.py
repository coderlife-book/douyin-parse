from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
VENV_DIR = ".venv"


def venv_python_path(root_dir: Path, os_name: str = os.name) -> Path:
    if os_name == "nt":
        return root_dir / VENV_DIR / "Scripts" / "python.exe"
    return root_dir / VENV_DIR / "bin" / "python"


def run_command(command: list[str], root_dir: Path = ROOT_DIR) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.check_call(command, cwd=root_dir)


def ensure_venv(root_dir: Path = ROOT_DIR) -> Path:
    venv_python = venv_python_path(root_dir)
    if not venv_python.exists():
        run_command([sys.executable, "-m", "venv", VENV_DIR], root_dir=root_dir)
    return venv_python


def install_dependencies(venv_python: Path, root_dir: Path = ROOT_DIR) -> None:
    run_command([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], root_dir=root_dir)
    run_command([str(venv_python), "-m", "playwright", "install", "chromium"], root_dir=root_dir)


def run_server(venv_python: Path, root_dir: Path = ROOT_DIR) -> int:
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "8787")
    print(f"启动本地服务：http://{host}:{port}/", flush=True)
    return subprocess.call([str(venv_python), "-m", "server_runtime"], cwd=root_dir, env=os.environ.copy())


def main() -> int:
    venv_python = ensure_venv()
    install_dependencies(venv_python)
    return run_server(venv_python)


if __name__ == "__main__":
    raise SystemExit(main())
