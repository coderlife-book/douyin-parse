#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python：$PYTHON_BIN"
  echo "请先安装 Python 3，或通过 PYTHON_BIN 指定 Python 可执行文件。"
  exit 1
fi

exec "$PYTHON_BIN" start.py
