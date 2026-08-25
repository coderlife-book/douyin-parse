from __future__ import annotations

import os
import threading
import webbrowser

from runtime_paths import browser_path
from server_runtime import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    build_service_url,
    start_background_server,
    stop_background_server,
)


def configure_bundled_browser() -> None:
    path = browser_path()
    if path.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)


def configure_reused_runtime() -> None:
    root = browser_path().parent
    additions = [root / "runtime" / "python", root / "runtime" / "ffmpeg"]
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*(str(path) for path in additions if path.is_dir()), existing])


def wait_until_exit() -> None:
    print("抖音视频工具正在运行。关闭此窗口或按 Ctrl+C 即可退出。", flush=True)
    threading.Event().wait()


def main() -> int:
    configure_reused_runtime()
    configure_bundled_browser()
    handle = start_background_server()
    if os.environ.get("DOUYIN_PARSE_NO_BROWSER") != "1":
        webbrowser.open(build_service_url(DEFAULT_HOST, DEFAULT_PORT))
    if handle is None:
        return 0
    try:
        wait_until_exit()
    except KeyboardInterrupt:
        pass
    finally:
        stop_background_server(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
