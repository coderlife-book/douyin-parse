from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


@dataclass
class ServerHandle:
    server: object
    thread: threading.Thread


def build_service_url(host: str, port: int, path: str = "/") -> str:
    path = path if path.startswith("/") else f"/{path}"
    url_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in url_host and not url_host.startswith("["):
        url_host = f"[{url_host}]"
    return f"http://{url_host}:{port}{path}"


def is_service_ready(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    request = urllib.request.Request(build_service_url(host, port, "/health"))
    try:
        with urllib.request.urlopen(request, timeout=0.5) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def wait_for_service(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    timeout: float = 20,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_service_ready(host, port):
            return True
        time.sleep(0.2)
    return False


def start_background_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    timeout: float = 20,
    log_level: str = "info",
) -> ServerHandle | None:
    if is_service_ready(host, port):
        return None

    import uvicorn

    config = uvicorn.Config("api_server:app", host=host, port=port, log_level=log_level)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="douyin-api-server", daemon=True)
    thread.start()

    if not wait_for_service(host, port, timeout=timeout):
        server.should_exit = True
        thread.join(timeout=3)
        raise RuntimeError(f"本地服务启动超时：{build_service_url(host, port, '/health')}")

    return ServerHandle(server=server, thread=thread)


def stop_background_server(handle: ServerHandle | None, timeout: float = 5) -> None:
    if handle is None:
        return
    handle.server.should_exit = True
    handle.thread.join(timeout=timeout)


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, log_level: str = "info") -> None:
    import uvicorn

    uvicorn.run("api_server:app", host=host, port=port, log_level=log_level)


def main() -> None:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    serve(host=host, port=port)


if __name__ == "__main__":
    main()
