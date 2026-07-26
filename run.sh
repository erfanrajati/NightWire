#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    printf 'NightWire requires uv. Install it from https://docs.astral.sh/uv/ and run this script again.\n' >&2
    exit 1
fi

export PORT="${NIGHTWIRE_PORT:-${PORT:-8080}}"
exec uv run --locked python app.py
