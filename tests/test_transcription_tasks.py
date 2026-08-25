import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.transcription_service import TranscriptSegment, TranscriptionResult
from services.transcription_tasks import TranscriptionTaskManager


class ConcurrencyTracker:
    def __init__(self):
        self.active = 0
        self.maximum = 0
        self.lock = threading.Lock()

    def transcribe(self, path, *, progress_cb):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            time.sleep(0.05)
            progress_cb(
                {
                    "segment_count": 1,
                    "processed_duration": 2.0,
                    "duration": 2.0,
                }
            )
            return make_transcription("并发测试")
        finally:
            with self.lock:
                self.active -= 1


def make_transcription(text="中文文案"):
    return TranscriptionResult(
        duration=2.0,
        language="zh",
        segments=[TranscriptSegment(start=0.0, end=2.0, text=text)],
        text=text,
    )


def fake_downloader(url, *, cookie, save_dir, progress_cb=None):
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    video_path = save_path / "source.mp4"
    video_path.write_bytes(b"video")
    if progress_cb:
        progress_cb(100, 5, 5)
    return SimpleNamespace(
        path=str(video_path),
        filename="source.mp4",
        aweme_id="7420000000000000000",
        desc="测试视频",
        author_nickname="测试作者",
    )


class TranscriptionTaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "transcripts"
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.temp_dir.cleanup()

    def make_manager(self, *, transcriber=None):
        manager = TranscriptionTaskManager(
            root=self.root,
            downloader=fake_downloader,
            transcriber=transcriber or (lambda path, *, progress_cb: make_transcription()),
        )
        self.managers.append(manager)
        return manager

    def wait_terminal(self, *tasks):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if all(task.status in {"done", "failed"} for task in tasks):
                return
            time.sleep(0.01)
        self.fail("字幕任务未在测试时限内结束")

    def test_executor_never_runs_two_transcriptions_together(self):
        tracker = ConcurrencyTracker()
        manager = self.make_manager(transcriber=tracker.transcribe)

        first = manager.create_task("https://v.douyin.com/1", cookie="sid=1")
        second = manager.create_task("https://v.douyin.com/2", cookie="sid=1")
        self.wait_terminal(first, second)

        self.assertEqual(first.status, "done")
        self.assertEqual(second.status, "done")
        self.assertEqual(tracker.maximum, 1)

    def test_completed_task_writes_manifest_text_and_removes_temporary_media(self):
        manager = self.make_manager()

        task = manager.create_task("https://v.douyin.com/1", cookie="sid=1")
        self.wait_terminal(task)

        task_dir = self.root / task.task_id
        manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((task_dir / "transcript.txt").read_text(encoding="utf-8"), "中文文案")
        self.assertEqual(manifest["status"], "done")
        self.assertEqual(manifest["author_nickname"], "测试作者")
        self.assertEqual(manifest["segments"], [{"start": 0.0, "end": 2.0, "text": "中文文案"}])
        self.assertFalse((task_dir / "temp").exists())

    def test_restart_marks_unfinished_manifest_interrupted(self):
        task_dir = self.root / "task-running"
        task_dir.mkdir(parents=True)
        (task_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "task_id": "task-running",
                    "source_url": "https://v.douyin.com/1",
                    "status": "transcribing",
                    "message": "正在识别语音",
                    "created_at": 1.0,
                    "updated_at": 2.0,
                    "segments": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        manager = self.make_manager()
        restored = manager.get_task("task-running")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, "interrupted")
        self.assertEqual(restored.message, "上次运行被中断，请重新识别")

    def test_failed_transcription_persists_error_and_removes_temporary_media(self):
        def fail_transcription(path, *, progress_cb):
            raise RuntimeError("模型读取失败")

        manager = self.make_manager(transcriber=fail_transcription)

        task = manager.create_task("https://v.douyin.com/1", cookie="sid=1")
        self.wait_terminal(task)

        task_dir = self.root / task.task_id
        manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(task.status, "failed")
        self.assertEqual(manifest["error"], "模型读取失败")
        self.assertFalse((task_dir / "temp").exists())


if __name__ == "__main__":
    unittest.main()
