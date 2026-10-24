#!/usr/bin/env bash
# Upgrade this machine's installed client or server, preserving configuration.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/deploy.py" upgrade "$@"
