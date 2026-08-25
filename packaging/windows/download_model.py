from __future__ import annotations

import argparse
from pathlib import Path

from app_meta import MODEL_REPOSITORY, MODEL_REVISION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_REPOSITORY,
        revision=MODEL_REVISION,
        local_dir=str(destination),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
