#!/usr/bin/env bash
# Install the DevLog server, local database, systemd service, and CLI.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/deploy.py" install-server "$@"
