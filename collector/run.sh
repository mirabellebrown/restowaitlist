#!/bin/bash
# Wrapper invoked by launchd (and handy for manual runs):
# activate the venv, load .env, run one collection cycle.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

exec .venv/bin/python collect.py
