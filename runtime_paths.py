from __future__ import annotations

import os
import sys
from pathlib import Path


ASR_MODELS = {
    "small": {
        "directory": "faster-whisper-small",
        "label": "Small",
        "description": "速度优先，推荐日常使用",
        "is_default": True,
    },
    "medium": {
        "directory": "faster-whisper-medium",
        "label": "Medium",
        "description": "效果更好，识别速度较慢",
        "is_default": False,
    },
}
ASR_MODEL_CORE_FILES = ("config.json", "model.bin", "tokenizer.json")


def portable_root() -> Path:
    override = os.environ.get("DOUYIN_PARSE_ROOT")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return portable_root() / "config.json"


def legacy_cookie_path() -> Path:
    return portable_root() / "douyin_cookie.txt"


def downloads_path() -> Path:
    return portable_root() / "downloads"


def transcripts_path() -> Path:
    return portable_root() / "data" / "transcripts"


def asr_model_path(model_id: str) -> Path:
    model = ASR_MODELS.get(model_id)
    if model is None:
        raise ValueError(f"不支持的 ASR 模型：{model_id}")
    return portable_root() / "models" / str(model["directory"])


def model_path() -> Path:
    return asr_model_path("small")


def available_asr_models() -> list[dict[str, object]]:
    available = []
    for model_id, metadata in ASR_MODELS.items():
        path = asr_model_path(model_id)
        if not all((path / filename).is_file() for filename in ASR_MODEL_CORE_FILES):
            continue
        available.append(
            {
                "id": model_id,
                "label": metadata["label"],
                "description": metadata["description"],
                "is_default": metadata["is_default"],
            }
        )
    return available


def browser_path() -> Path:
    return portable_root() / "browsers"


def portable_chromium_path() -> Path:
    return browser_path() / "chromium" / "chrome.exe"


def web_index_path() -> Path:
    return portable_root() / "web" / "index.html"
