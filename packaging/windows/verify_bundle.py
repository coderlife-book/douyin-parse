from __future__ import annotations

import sys
from pathlib import Path


CORE_FILES = {
    "抖音视频工具.exe",
    "version.json",
    "一键更新.bat",
    "更新工具.ps1",
    "web/index.html",
    "models/faster-whisper-small/config.json",
    "models/faster-whisper-small/model.bin",
    "models/faster-whisper-small/tokenizer.json",
}
NONEMPTY_DIRECTORIES = {"_internal", "browsers"}


def missing_core_paths(bundle: str | Path) -> set[str]:
    root = Path(bundle)
    missing = {relative for relative in CORE_FILES if not (root / relative).is_file()}
    for relative in NONEMPTY_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir() or not any(item.is_file() for item in directory.rglob("*")):
            missing.add(relative)
    return missing


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 1:
        print("用法：python verify_bundle.py <绿色版目录>", file=sys.stderr)
        return 2
    missing = missing_core_paths(args[0])
    if missing:
        print("绿色版缺少文件：" + "、".join(sorted(missing)), file=sys.stderr)
        return 1
    print("Windows portable bundle OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
