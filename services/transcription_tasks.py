from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from runtime_paths import transcripts_path
from services.download_service import download_video
from services.transcription_service import TranscriptSegment, TranscriptionResult, transcribe_media


ACTIVE_STATUSES = {"queued", "downloading", "loading_model", "transcribing"}


@dataclass
class TranscriptionTask:
    source_url: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    message: str = "等待识别"
    progress: int = 0
    downloaded: int = 0
    total: int = 0
    processed_duration: float = 0.0
    duration: float = 0.0
    segment_count: int = 0
    language: str = ""
    text: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    aweme_id: str = ""
    desc: str = ""
    author_nickname: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def set_state(self, **changes: Any) -> None:
        with self._lock:
            for name, value in changes.items():
                setattr(self, name, value)
            self.updated_at = time.time()

    def snapshot(self, *, include_segments: bool = False) -> dict[str, Any]:
        with self._lock:
            data = self.to_manifest()
        if not include_segments:
            data.pop("segments", None)
        return data

    def to_manifest(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source_url": self.source_url,
            "status": self.status,
            "message": self.message,
            "progress": self.progress,
            "downloaded": self.downloaded,
            "total": self.total,
            "processed_duration": self.processed_duration,
            "duration": self.duration,
            "segment_count": self.segment_count,
            "language": self.language,
            "text": self.text,
            "segments": [asdict(item) for item in self.segments],
            "aweme_id": self.aweme_id,
            "desc": self.desc,
            "author_nickname": self.author_nickname,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> "TranscriptionTask":
        allowed = {item.name for item in fields(cls) if item.init and item.name != "segments"}
        values = {name: data[name] for name in allowed if name in data}
        values["segments"] = [TranscriptSegment(**item) for item in data.get("segments") or []]
        return cls(**values)


class TranscriptionTaskManager:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        downloader: Callable[..., Any] = download_video,
        transcriber: Callable[..., TranscriptionResult] = transcribe_media,
    ) -> None:
        self.root = Path(root or transcripts_path())
        self.root.mkdir(parents=True, exist_ok=True)
        self._downloader = downloader
        self._transcriber = transcriber
        self._lock = threading.RLock()
        self._tasks: dict[str, TranscriptionTask] = {}
        self._stopping = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="douyin-asr")
        self._load_tasks()

    def create_task(self, url: str, *, cookie: str) -> TranscriptionTask:
        if self._stopping.is_set():
            raise RuntimeError("字幕任务管理器正在关闭")
        task = TranscriptionTask(source_url=url)
        with self._lock:
            self._tasks[task.task_id] = task
        self._persist(task)
        self._executor.submit(self._run_task, task, cookie)
        return task

    def get_task(self, task_id: str) -> TranscriptionTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[TranscriptionTask]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda item: item.updated_at, reverse=True)

    def text_path(self, task_id: str) -> Path:
        return self.root / task_id / "transcript.txt"

    def is_busy(self) -> bool:
        with self._lock:
            return any(task.status in ACTIVE_STATUSES for task in self._tasks.values())

    def close(self, *, wait: bool = True) -> None:
        self._stopping.set()
        for task in self.list_tasks():
            if task.status in ACTIVE_STATUSES:
                self._set_and_persist(
                    task,
                    status="interrupted",
                    message="程序已退出，请重新识别",
                    error="",
                )
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _load_tasks(self) -> None:
        for manifest_path in self.root.glob("*/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                task = TranscriptionTask.from_manifest(data)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if task.status in ACTIVE_STATUSES:
                shutil.rmtree(manifest_path.parent / "temp", ignore_errors=True)
                task.set_state(
                    status="interrupted",
                    message="上次运行被中断，请重新识别",
                    error="",
                )
                self._persist(task)
            self._tasks[task.task_id] = task

    def _persist(self, task: TranscriptionTask) -> None:
        task_dir = self.root / task.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        snapshot = task.to_manifest()
        if task.status == "done":
            (task_dir / "transcript.txt").write_text(task.text, encoding="utf-8")
        temporary = task_dir / "manifest.json.tmp"
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, task_dir / "manifest.json")

    def _set_and_persist(self, task: TranscriptionTask, **changes: Any) -> None:
        task.set_state(**changes)
        self._persist(task)

    def _run_task(self, task: TranscriptionTask, cookie: str) -> None:
        task_dir = self.root / task.task_id
        temp_dir = task_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._raise_if_stopping()
            self._set_and_persist(
                task,
                status="downloading",
                message="正在下载视频",
                progress=1,
            )

            def on_download(progress: int, downloaded: int, total: int) -> None:
                self._raise_if_stopping()
                self._set_and_persist(
                    task,
                    status="downloading",
                    message="正在下载视频",
                    progress=max(1, min(20, int(progress * 0.2))),
                    downloaded=downloaded,
                    total=total,
                )

            downloaded = self._downloader(
                task.source_url,
                cookie=cookie,
                save_dir=str(temp_dir),
                progress_cb=on_download,
            )
            self._raise_if_stopping()
            self._set_and_persist(
                task,
                status="loading_model",
                message="正在加载字幕模型",
                progress=25,
                aweme_id=str(getattr(downloaded, "aweme_id", "") or ""),
                desc=str(getattr(downloaded, "desc", "") or ""),
                author_nickname=str(getattr(downloaded, "author_nickname", "") or ""),
            )

            def on_transcription(progress: dict[str, float | int]) -> None:
                self._raise_if_stopping()
                duration = float(progress.get("duration") or 0)
                processed = float(progress.get("processed_duration") or 0)
                percent = 25
                if duration > 0:
                    percent = min(99, 25 + int(processed * 74 / duration))
                self._set_and_persist(
                    task,
                    status="transcribing",
                    message="正在识别语音",
                    progress=percent,
                    segment_count=int(progress.get("segment_count") or 0),
                    processed_duration=processed,
                    duration=duration,
                )

            result = self._transcriber(downloaded.path, progress_cb=on_transcription)
            self._raise_if_stopping()
            if not result.text.strip():
                raise ValueError("未识别到可用的语音文案")
            self._set_and_persist(
                task,
                status="done",
                message="字幕识别完成",
                progress=100,
                processed_duration=result.duration,
                duration=result.duration,
                segment_count=len(result.segments),
                language=result.language,
                text=result.text,
                segments=result.segments,
                error="",
            )
        except Exception as exc:
            if self._stopping.is_set():
                self._set_and_persist(
                    task,
                    status="interrupted",
                    message="程序已退出，请重新识别",
                    error="",
                )
            else:
                self._set_and_persist(
                    task,
                    status="failed",
                    message=str(exc),
                    error=str(exc),
                )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _raise_if_stopping(self) -> None:
        if self._stopping.is_set():
            raise InterruptedError("程序正在退出")
