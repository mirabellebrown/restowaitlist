#!/bin/bash
# Wrapper invoked by launchd (and handy for manual runs):
# activate the venv, load .env, run one collection cycle.
#
# Variables already set in the environment (e.g. RWL_DRY_RUN=true ./run.sh)
# take precedence over values in .env.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*|[[:space:]]*) continue ;;
    esac
    key="${line%%=*}"
    # Skip if the caller already exported this variable.
    if [ -n "${!key+x}" ]; then
      continue
    fi
    export "$line"
  done < .env
fi

exec .venv/bin/python collect.py
