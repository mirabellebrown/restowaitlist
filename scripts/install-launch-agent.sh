#!/bin/zsh
# Install the safe local scheduler for the current macOS login session.
set -euo pipefail

script_dir="${0:A:h}"
repo_root="$(git -C "$script_dir/.." rev-parse --show-toplevel)"
label="com.restowaitlist.waitwatch"
template="$repo_root/ops/$label.plist"
destination="$HOME/Library/LaunchAgents/$label.plist"

if [[ ! -f "$template" ]]; then
  print -u2 "LaunchAgent template not found: $template"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$repo_root/logs"
temporary="$(mktemp "${TMPDIR:-/tmp}/$label.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
sed "s|__REPO_ROOT__|$repo_root|g" "$template" > "$temporary"
mv "$temporary" "$destination"

launchctl bootout "gui/$UID/$label" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$destination"
launchctl kickstart -k "gui/$UID/$label"
print "Installed and started $label. It runs at 1, 16, 31, and 46 minutes past each hour."
