#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
uv run --frozen python scripts/project_status.py --check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest

