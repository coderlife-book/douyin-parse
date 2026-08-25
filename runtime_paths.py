from __future__ import annotations

import os
import sys
from pathlib import Path


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


def model_path() -> Path:
    return portable_root() / "models" / "faster-whisper-small"


def browser_path() -> Path:
    return portable_root() / "browsers"


def web_index_path() -> Path:
    return portable_root() / "web" / "index.html"
