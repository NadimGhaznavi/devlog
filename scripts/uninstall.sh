#!/usr/bin/env bash
# Remove all DevLog installation files and data, preserving only credentials.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/deploy.py" uninstall "$@"
