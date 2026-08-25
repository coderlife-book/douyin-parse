import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import api_server


class FakeTask:
    def __init__(self, task_id, status="queued", text="", *, segments=None):
        self.task_id = task_id
        self.status = status
        self.text = text
        self.segments = segments or []

    def snapshot(self, *, include_segments=False):
        data = {
            "task_id": self.task_id,
            "status": self.status,
            "message": "字幕识别完成" if self.status == "done" else "等待识别",
            "text": self.text,
        }
        if include_segments:
            data["segments"] = self.segments
        return data


class FakeLoginManager:
    def __init__(self):
        self.cookie = ""

    def get_cookie(self, session_id=None):
        return self.cookie


class FakeTranscriptionManager:
    def __init__(self, root):
        self.root = Path(root)
        self.tasks = {
            "running": FakeTask("running", "transcribing"),
            "done": FakeTask(
                "done",
                "done",
                "中文文案",
                segments=[{"start": 0.0, "end": 1.0, "text": "中文文案"}],
            ),
        }
        done_dir = self.root / "done"
        done_dir.mkdir(parents=True)
        (done_dir / "transcript.txt").write_text("中文文案", encoding="utf-8")
        self.create_calls = []

    def create_task(self, url, *, cookie, model):
        self.create_calls.append((url, cookie, model))
        task = FakeTask("created")
        self.tasks[task.task_id] = task
        return task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def list_tasks(self):
        return [self.tasks["done"], self.tasks["running"]]

    def text_path(self, task_id):
        return self.root / task_id / "transcript.txt"

    def is_busy(self):
        return True


class TranscriptionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.login_manager = FakeLoginManager()
        self.task_manager = FakeTranscriptionManager(self.temp_dir.name)
        self.patchers = [
            mock.patch.object(api_server, "login_manager", self.login_manager),
            mock.patch.object(api_server, "transcription_task_manager", self.task_manager, create=True),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(api_server.app)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_create_requires_login(self):
        response = self.client.post(
            "/transcription/tasks",
            json={"url": "https://v.douyin.com/demo"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "请先扫码登录抖音")

    def test_create_returns_queued_task_snapshot(self):
        self.login_manager.cookie = "sessionid=abc"

        with mock.patch.object(
            api_server,
            "available_asr_models",
            return_value=[{"id": "small", "label": "Small", "description": "速度优先", "is_default": True}],
        ):
            response = self.client.post(
                "/transcription/tasks",
                json={"url": "https://v.douyin.com/demo"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "created")
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(
            self.task_manager.create_calls,
            [("https://v.douyin.com/demo", "sessionid=abc", "small")],
        )

    def test_available_models_endpoint_only_returns_local_models(self):
        expected = [
            {
                "id": "medium",
                "label": "Medium",
                "description": "效果更好，识别速度较慢",
                "is_default": False,
            }
        ]
        with mock.patch.object(api_server, "available_asr_models", return_value=expected):
            response = self.client.get("/asr/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_create_rejects_model_that_is_not_available_locally(self):
        self.login_manager.cookie = "sessionid=abc"
        with mock.patch.object(api_server, "available_asr_models", return_value=[]):
            response = self.client.post(
                "/transcription/tasks",
                json={"url": "https://v.douyin.com/demo", "model": "medium"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "本地 ASR 模型不可用：medium")
        self.assertEqual(self.task_manager.create_calls, [])

    def test_list_and_detail_return_persisted_tasks(self):
        listed = self.client.get("/transcription/tasks")
        detailed = self.client.get("/transcription/tasks/done")

        self.assertEqual([item["task_id"] for item in listed.json()], ["done", "running"])
        self.assertEqual(
            detailed.json()["segments"],
            [{"start": 0.0, "end": 1.0, "text": "中文文案"}],
        )

    def test_text_returns_conflict_until_task_is_done(self):
        response = self.client.get("/transcription/tasks/running/text")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "字幕任务尚未完成")

    def test_detail_returns_not_found_for_unknown_task(self):
        response = self.client.get("/transcription/tasks/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "字幕任务不存在")

    def test_text_download_is_utf8_plain_text(self):
        response = self.client.get("/transcription/tasks/done/text")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "中文文案")
        self.assertEqual(response.headers["content-type"], "text/plain; charset=utf-8")

    def test_health_exposes_version_model_and_queue_state(self):
        with mock.patch.object(api_server, "available_asr_models", return_value=[]):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], "1.2.0")
        self.assertFalse(response.json()["asr_model_ready"])
        self.assertTrue(response.json()["transcription_busy"])


if __name__ == "__main__":
    unittest.main()
