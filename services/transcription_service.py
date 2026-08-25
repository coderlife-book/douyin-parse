from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from runtime_paths import model_path


ProgressCallback = Callable[[dict[str, float | int]], None]


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

    def get(self):
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


DEFAULT_MODEL_PROVIDER = WhisperModelProvider(model_path())


def transcribe_media(
    path: str | Path,
    *,
    progress_cb: ProgressCallback | None = None,
    provider: WhisperModelProvider | None = None,
) -> TranscriptionResult:
    model = (provider or DEFAULT_MODEL_PROVIDER).get()
    raw_segments, info = model.transcribe(
        str(path),
        beam_size=5,
        vad_filter=True,
    )
    duration = float(info.duration or 0)
    segments: list[TranscriptSegment] = []

    for raw in raw_segments:
        text = raw.text.strip()
        if text:
            segments.append(
                TranscriptSegment(
                    start=float(raw.start),
                    end=float(raw.end),
                    text=text,
                )
            )
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
        text="".join(item.text for item in segments),
    )
