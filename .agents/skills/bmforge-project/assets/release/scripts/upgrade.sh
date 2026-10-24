#!/usr/bin/env bash
# Upgrade an installation while retaining configuration, credentials, and data.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec python3 -B scripts/install.py upgrade "$@"
