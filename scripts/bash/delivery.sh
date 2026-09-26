#!/usr/bin/env bash
set -euo pipefail
extension_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec uv run --script "$extension_root/scripts/python/delivery.py" "$@"
