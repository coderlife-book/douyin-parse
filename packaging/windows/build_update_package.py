from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from update_manifest import EXCLUDED_TOP_LEVEL, build_manifest


def copy_core_payload(bundle: Path, payload: Path) -> None:
    payload.mkdir(parents=True, exist_ok=True)
    for source in sorted(bundle.iterdir()):
        if source.name in EXCLUDED_TOP_LEVEL:
            continue
        destination = payload / source.name
        if source.is_dir():
            shutil.copytree(source, destination)
        elif source.is_file():
            shutil.copy2(source, destination)


def create_update_package(
    bundle: str | Path,
    output: str | Path,
    *,
    version: str,
    minimum_version: str,
) -> Path:
    bundle_path = Path(bundle).resolve()
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir)
        payload = staging / "payload"
        copy_core_payload(bundle_path, payload)
        manifest = build_manifest(payload, version, minimum_version)
        (staging / "update-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(item for item in staging.rglob("*") if item.is_file()):
                archive.write(path, path.relative_to(staging).as_posix())
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--minimum-version", required=True)
    args = parser.parse_args(argv)
    output = create_update_package(
        args.bundle,
        args.output,
        version=args.version,
        minimum_version=args.minimum_version,
    )
    print(f"更新包已生成：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
