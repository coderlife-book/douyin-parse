from __future__ import annotations

import gc
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from opencc import OpenCC

from runtime_paths import asr_model_path


ProgressCallback = Callable[[dict[str, float | int]], None]
SIMPLIFIED_CHINESE_CONVERTER = OpenCC("t2s")


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    duration: float
    language: str
    segments: list[TranscriptSegment]
    text: str


def _load_whisper_model(path: str, **kwargs):
    from faster_whisper import WhisperModel

    return WhisperModel(path, **kwargs)


class WhisperModelProvider:
    def __init__(
        self,
        path: Path,
        *,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._path = Path(path)
        self._model_factory = model_factory or _load_whisper_model
        self._model = None
        self._lock = threading.Lock()

    def get(self, model_name: str = "small"):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self._path.exists():
                raise FileNotFoundError(f"ASR 模型不存在：{self._path}")
            self._model = self._model_factory(
                str(self._path),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            )
            return self._model


class SwitchingWhisperModelProvider:
    def __init__(
        self,
        *,
        model_path_resolver: Callable[[str], Path] = asr_model_path,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model_path_resolver = model_path_resolver
        self._model_factory = model_factory or _load_whisper_model
        self._model_name = ""
        self._model = None
        self._lock = threading.Lock()

    def get(self, model_name: str = "small"):
        with self._lock:
            if self._model is not None and self._model_name == model_name:
                return self._model
            path = Path(self._model_path_resolver(model_name))
            if not path.exists():
                raise FileNotFoundError(f"ASR 模型不存在：{path}")
            self._model = None
            self._model_name = ""
            gc.collect()
            self._model = self._model_factory(
                str(path),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            )
            self._model_name = model_name
            return self._model


DEFAULT_MODEL_PROVIDER = SwitchingWhisperModelProvider()


def _join_segment_texts(
    segments: list[TranscriptSegment],
    leading_spaces: list[bool],
) -> str:
    text = ""
    closing_punctuation = ".,!?;:%)]}，。！？；：、）》】」』”’…"
    for index, segment in enumerate(segments):
        implicit_word_boundary = (
            text
            and text[-1].isascii()
            and text[-1].isalnum()
            and segment.text[0].isascii()
            and segment.text[0].isalnum()
        )
        explicit_model_boundary = (
            text
            and leading_spaces[index]
            and text[-1].isascii()
            and segment.text[0].isascii()
            and segment.text[0] not in closing_punctuation
        )
        if implicit_word_boundary or explicit_model_boundary:
            text += " "
        elif (
            text
            and "\u3400" <= text[-1] <= "\u9fff"
            and "\u3400" <= segment.text[0] <= "\u9fff"
            and text[-1] not in closing_punctuation
            and segment.text[0] not in closing_punctuation
        ):
            text += "，"
        text += segment.text
    if any("\u3400" <= char <= "\u9fff" for char in text):
        closing_delimiters = "”’\"'）)]】》」』"
        core = text.rstrip(closing_delimiters)
        suffix = text[len(core) :]
        if core.endswith(("，", ",", "；", ";", "：", ":")):
            core = core[:-1] + "。"
        elif not core.endswith(("。", ".", "！", "？", "!", "?", "…")):
            core += "。"
        text = core + suffix
    return text


def transcribe_media(
    path: str | Path,
    *,
    model_name: str = "small",
    progress_cb: ProgressCallback | None = None,
    provider: WhisperModelProvider | SwitchingWhisperModelProvider | None = None,
) -> TranscriptionResult:
    model = (provider or DEFAULT_MODEL_PROVIDER).get(model_name)
    raw_segments, info = model.transcribe(
        str(path),
        beam_size=5,
        vad_filter=True,
    )
    duration = float(info.duration or 0)
    segments: list[TranscriptSegment] = []
    leading_spaces: list[bool] = []

    for raw in raw_segments:
        raw_text = str(raw.text or "")
        text = SIMPLIFIED_CHINESE_CONVERTER.convert(raw_text.strip())
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "，", text)
        if text:
            segments.append(
                TranscriptSegment(
                    start=float(raw.start),
                    end=float(raw.end),
                    text=text,
                )
            )
            leading_spaces.append(bool(raw_text[:1].isspace()))
        if progress_cb:
            progress_cb(
                {
                    "segment_count": len(segments),
                    "processed_duration": float(raw.end),
                    "duration": duration,
                }
            )

    return TranscriptionResult(
        duration=duration,
        language=str(info.language or ""),
        segments=segments,
        text=_join_segment_texts(segments, leading_spaces),
    )
