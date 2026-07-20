#!/bin/zsh
# Called by launchd. It reads a locally supplied snapshot, exports the table,
# and publishes only the static-site branch. It never opens a restaurant page.
set -euo pipefail

script_dir="${0:A:h}"
repo_root="$(git -C "$script_dir/.." rev-parse --show-toplevel)"
config_path="${WAITWATCH_CONFIG:-$repo_root/config.toml}"
python_bin="${WAITWATCH_PYTHON:-$repo_root/.venv/bin/python}"

mkdir -p "$repo_root/logs"
if [[ ! -f "$config_path" ]]; then
  print "No local config at $config_path; nothing to sync."
  exit 0
fi
if [[ ! -x "$python_bin" ]]; then
  print -u2 "Python environment not found: $python_bin"
  exit 1
fi

"$python_bin" -m dtf_waitwatch sync-snapshot \
  --config "$config_path" \
  --output "$repo_root/site/data/waits.json" \
  --days "${WAITWATCH_HISTORY_DAYS:-31}" \
  --max-age-minutes "${WAITWATCH_MAX_AGE_MINUTES:-30}"
"$script_dir/publish-pages.sh" "$repo_root/site"
