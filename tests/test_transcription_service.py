import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.transcription_service import (
    SwitchingWhisperModelProvider,
    WhisperModelProvider,
    transcribe_media,
)


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

    def get(self, model_name="small"):
        return self.model


class TranscriptionServiceTests(unittest.TestCase):
    def test_switching_provider_reuses_selected_model_and_releases_on_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = {
                "small": root / "faster-whisper-small",
                "medium": root / "faster-whisper-medium",
            }
            for path in paths.values():
                path.mkdir()
            created = []

            def factory(path, **kwargs):
                model = SimpleNamespace(path=path)
                created.append(model)
                return model

            provider = SwitchingWhisperModelProvider(
                model_path_resolver=paths.__getitem__,
                model_factory=factory,
            )

            first = provider.get("small")
            second = provider.get("small")
            medium = provider.get("medium")

        self.assertIs(first, second)
        self.assertIsNot(first, medium)
        self.assertEqual(
            [item.path for item in created],
            [str(paths["small"]), str(paths["medium"])],
        )

    def test_transcribe_requests_selected_model_from_provider(self):
        class RecordingProvider(FakeProvider):
            def __init__(self, model):
                super().__init__(model)
                self.requested = []

            def get(self, model_name="small"):
                self.requested.append(model_name)
                return self.model

        provider = RecordingProvider(FakeModel())

        transcribe_media("demo.mp4", model_name="medium", provider=provider)

        self.assertEqual(provider.requested, ["medium"])

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

        self.assertEqual(result.text, "你好，世界。")
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

    def test_transcribe_preserves_space_after_english_punctuation(self):
        class EnglishModel:
            def transcribe(self, path, **kwargs):
                segments = [
                    SimpleNamespace(start=0.0, end=1.0, text=" Hello."),
                    SimpleNamespace(start=1.0, end=2.0, text=" How are you?"),
                ]
                return iter(segments), SimpleNamespace(duration=2.0, language="en")

        result = transcribe_media("demo.mp4", provider=FakeProvider(EnglishModel()))

        self.assertEqual(result.text, "Hello. How are you?")

    def test_transcribe_converts_traditional_chinese_segments_to_simplified(self):
        class TraditionalChineseModel:
            def transcribe(self, path, **kwargs):
                segments = [
                    SimpleNamespace(start=0.0, end=1.0, text=" 這是繁體字 "),
                    SimpleNamespace(start=1.0, end=2.0, text=" 軟體與影片 "),
                ]
                return iter(segments), SimpleNamespace(duration=2.0, language="zh")

        result = transcribe_media(
            "demo.mp4",
            provider=FakeProvider(TraditionalChineseModel()),
        )

        self.assertEqual(result.text, "这是繁体字，软体与影片。")
        self.assertEqual(
            [item.text for item in result.segments],
            ["这是繁体字", "软体与影片"],
        )

    def test_transcribe_does_not_duplicate_existing_chinese_punctuation(self):
        class PunctuatedChineseModel:
            def transcribe(self, path, **kwargs):
                segments = [
                    SimpleNamespace(start=0.0, end=1.0, text="这是第一句。"),
                    SimpleNamespace(start=1.0, end=2.0, text="这是第二句！"),
                ]
                return iter(segments), SimpleNamespace(duration=2.0, language="zh")

        result = transcribe_media(
            "demo.mp4",
            provider=FakeProvider(PunctuatedChineseModel()),
        )

        self.assertEqual(result.text, "这是第一句。这是第二句！")

    def test_transcribe_replaces_spaces_between_chinese_clauses_with_commas(self):
        class SpacedChineseModel:
            def transcribe(self, path, **kwargs):
                segments = [SimpleNamespace(start=0.0, end=1.0, text="成功 要么成长")]
                return iter(segments), SimpleNamespace(duration=1.0, language="zh")

        result = transcribe_media(
            "demo.mp4",
            provider=FakeProvider(SpacedChineseModel()),
        )

        self.assertEqual(result.text, "成功，要么成长。")
        self.assertEqual(result.segments[0].text, "成功，要么成长")

    def test_transcribe_accepts_ascii_period_as_existing_chinese_terminator(self):
        class AsciiPeriodModel:
            def transcribe(self, path, **kwargs):
                segments = [SimpleNamespace(start=0.0, end=1.0, text="当前版本2.0.")]
                return iter(segments), SimpleNamespace(duration=1.0, language="zh")

        result = transcribe_media("demo.mp4", provider=FakeProvider(AsciiPeriodModel()))

        self.assertEqual(result.text, "当前版本2.0.")

    def test_transcribe_checks_punctuation_before_closing_chinese_quote(self):
        class QuotedChineseModel:
            def transcribe(self, path, **kwargs):
                segments = [SimpleNamespace(start=0.0, end=1.0, text="他说“你好。”")]
                return iter(segments), SimpleNamespace(duration=1.0, language="zh")

        result = transcribe_media("demo.mp4", provider=FakeProvider(QuotedChineseModel()))

        self.assertEqual(result.text, "他说“你好。”")


if __name__ == "__main__":
    unittest.main()
