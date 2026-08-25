import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.transcription_service import WhisperModelProvider, transcribe_media


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        segments = [
            SimpleNamespace(start=0.0, end=1.5, text=" 你好 "),
            SimpleNamespace(start=1.5, end=3.0, text=" 世界 "),
        ]
        info = SimpleNamespace(duration=3.0, language="zh")
        return iter(segments), info


class FakeProvider:
    def __init__(self, model):
        self.model = model

    def get(self):
        return self.model


class TranscriptionServiceTests(unittest.TestCase):
    def test_provider_loads_local_model_on_cpu_int8_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir)
            (model_dir / "config.json").write_text("{}", encoding="utf-8")
            factory = mock.Mock(return_value=object())
            provider = WhisperModelProvider(model_dir, model_factory=factory)

            first = provider.get()
            second = provider.get()

        self.assertIs(first, second)
        factory.assert_called_once_with(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
        )

    def test_provider_rejects_missing_bundled_model_before_importing_runtime(self):
        factory = mock.Mock()
        provider = WhisperModelProvider(Path("/missing/faster-whisper-small"), model_factory=factory)

        with self.assertRaisesRegex(FileNotFoundError, "ASR 模型不存在"):
            provider.get()

        factory.assert_not_called()

    def test_transcribe_joins_real_segments_and_reports_audio_progress(self):
        model = FakeModel()
        progress = []

        result = transcribe_media(
            "demo.mp4",
            progress_cb=progress.append,
            provider=FakeProvider(model),
        )

        self.assertEqual(result.text, "你好世界")
        self.assertEqual(result.duration, 3.0)
        self.assertEqual(result.language, "zh")
        self.assertEqual(
            [(item.start, item.end, item.text) for item in result.segments],
            [(0.0, 1.5, "你好"), (1.5, 3.0, "世界")],
        )
        self.assertEqual(
            progress,
            [
                {"segment_count": 1, "processed_duration": 1.5, "duration": 3.0},
                {"segment_count": 2, "processed_duration": 3.0, "duration": 3.0},
            ],
        )
        self.assertEqual(
            model.calls,
            [("demo.mp4", {"beam_size": 5, "vad_filter": True})],
        )

    def test_transcribe_preserves_english_word_boundaries(self):
        class EnglishModel:
            def transcribe(self, path, **kwargs):
                segments = [
                    SimpleNamespace(start=0.0, end=1.0, text=" Hello "),
                    SimpleNamespace(start=1.0, end=2.0, text=" world "),
                ]
                return iter(segments), SimpleNamespace(duration=2.0, language="en")

        result = transcribe_media("demo.mp4", provider=FakeProvider(EnglishModel()))

        self.assertEqual(result.text, "Hello world")
        self.assertEqual([item.text for item in result.segments], ["Hello", "world"])


if __name__ == "__main__":
    unittest.main()
