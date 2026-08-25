from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath


EXCLUDED_TOP_LEVEL = {
    "config.json",
    "data",
    "downloads",
    "models",
    "browsers",
    "_rollback",
    "update-temp",
    "一键更新.bat",
    "更新工具.ps1",
}


def validate_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or path.parts[0].endswith(":")
    ):
        raise ValueError(f"非法更新路径：{value}")
    return path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    payload_root: str | Path,
    version: str,
    minimum_version: str,
) -> dict:
    root = Path(payload_root)
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        validated = validate_relative_path(relative)
        if validated.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "protocol": 1,
        "version": version,
        "minimum_version": minimum_version,
        "files": files,
    }
