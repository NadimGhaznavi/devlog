#!/usr/bin/env bash
# Remove DevLog-managed client/server code while retaining user configuration and data.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/deploy.py" uninstall "$@"
