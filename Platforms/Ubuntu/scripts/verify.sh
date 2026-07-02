#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m py_compile $(find codexu_ubuntu -name '*.py' -print)
python3 -m unittest discover -s tests

TMP_CODEX_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_CODEX_HOME"' EXIT
CODEX_HOME="$TMP_CODEX_HOME" python3 -m codexu_ubuntu --dump-json --no-app-server >/tmp/codexu-ubuntu-dump.json
