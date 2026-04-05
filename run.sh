#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

exec "$DIR/venv/bin/python3" "$DIR/main.py" run "$@"
