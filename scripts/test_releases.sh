#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT_DIR/scripts/test_release_compiler.py"
python3 "$ROOT_DIR/scripts/test_compose_renderer.py"
python3 "$ROOT_DIR/scripts/test_releases_api.py"
python3 "$ROOT_DIR/scripts/test_release_integration.py"
