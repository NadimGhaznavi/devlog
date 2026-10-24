#!/usr/bin/env bash
# Install only dl; requires -server <IP or hostname>.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/deploy.py" install "$@"
