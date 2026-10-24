#!/usr/bin/env bash
# Provision and deploy the project from a separate source checkout.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec python3 -B scripts/install.py install "$@"
