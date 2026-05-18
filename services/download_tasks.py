import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from services.download_service import DownloadResult, download_video


@dataclass
class DownloadTask:
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    message: str = "等待下载"
    progress: int = 0
    downloaded: int = 0
    total: int = 0
    result: DownloadResult | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = {
                "task_id": self.task_id,
                "status": self.status,
                "message": self.message,
                "progress": self.progress,
                "downloaded": self.downloaded,
                "total": self.total,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
            if self.result:
                data["filename"] = self.result.filename
                data["aweme_id"] = self.result.aweme_id
            if self.error:
                data["error"] = self.error
            return data

    def set_state(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.updated_at = time.time()


class DownloadTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.RLock()

    def create_task(self, url: str, *, cookie: str, quality: str | None = None) -> DownloadTask:
        task = DownloadTask()
        with self._lock:
            self._tasks[task.task_id] = task

        thread = threading.Thread(
            target=self._run_task,
            args=(task, url, cookie, quality),
            daemon=True,
        )
        thread.start()
        return task

    def get_task(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    @staticmethod
    def _run_task(task: DownloadTask, url: str, cookie: str, quality: str | None) -> None:
        task.set_state(status="running", message="正在解析视频", progress=1)

        def on_progress(progress: int, downloaded: int, total: int) -> None:
            task.set_state(
                status="running",
                message="正在下载视频",
                progress=max(1, progress),
                downloaded=downloaded,
                total=total,
            )

        try:
            result = download_video(url, cookie=cookie, quality=quality, progress_cb=on_progress)
            task.set_state(
                status="done",
                message="下载完成",
                progress=100,
                result=result,
            )
        except Exception as exc:
            task.set_state(
                status="failed",
                message=str(exc),
                error=str(exc),
            )
