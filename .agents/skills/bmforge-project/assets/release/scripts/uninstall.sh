#!/usr/bin/env bash
# Remove project-managed deployment files while retaining persistent state.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec python3 -B scripts/install.py uninstall "$@"
