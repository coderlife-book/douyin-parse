from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_meta import ASR_MODEL_RELEASES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True)
    parser.add_argument("--model", choices=ASR_MODEL_RELEASES, default="small")
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    repository, revision = ASR_MODEL_RELEASES[args.model]
    snapshot_download(
        repo_id=repository,
        revision=revision,
        local_dir=str(destination),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
