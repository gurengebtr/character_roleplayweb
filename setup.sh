#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${1:-}" == "--check" ]]; then
  if [[ ! -x .venv/bin/python ]]; then echo 'Missing environment. Run ./setup.sh first.'; exit 1; fi
  exec .venv/bin/python scripts/setup.py --check
fi
command -v docker >/dev/null || { echo 'Install Docker Desktop or Docker Engine + Compose first.'; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Start Docker, then run ./setup.sh again.'; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 22+ first.'; exit 1; }
PYTHON="${PYTHON_BIN:-python3.12}"
command -v "$PYTHON" >/dev/null || PYTHON=python3
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
[[ -x .venv/bin/python ]] || "$PYTHON" -m venv .venv
if [[ -f requirements.lock ]]; then
  .venv/bin/python -m pip install -q -r requirements.lock
else
  .venv/bin/python -m pip install -q .
fi
if [[ -f package-lock.json ]]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
exec .venv/bin/python scripts/setup.py
