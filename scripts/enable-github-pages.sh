#!/bin/zsh
# Point the current fork's GitHub Pages setting at the publisher's gh-pages branch.
set -euo pipefail

branch="${WAITWATCH_PAGES_BRANCH:-gh-pages}"
if [[ -n "${WAITWATCH_PAGES_REPOSITORY:-}" ]]; then
  repository="$WAITWATCH_PAGES_REPOSITORY"
else
  origin_url="$(git remote get-url origin)"
  repository="$(print -r -- "$origin_url" | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##')"
fi
if [[ "$repository" != */* ]]; then
  print -u2 "Could not derive an owner/repository from origin: ${origin_url:-$repository}"
  exit 1
fi
payload="{\"build_type\":\"legacy\",\"source\":{\"branch\":\"$branch\",\"path\":\"/\"}}"

if gh api "repos/$repository/pages" >/dev/null 2>&1; then
  print -r -- "$payload" | gh api --method PUT "repos/$repository/pages" --input - >/dev/null
elif ! print -r -- "$payload" | gh api --method POST "repos/$repository/pages" --input - >/dev/null; then
  # A concurrent enablement can return 409 before the read endpoint is ready.
  print -r -- "$payload" | gh api --method PUT "repos/$repository/pages" --input - >/dev/null
fi

for attempt in 1 2 3 4 5; do
  page_url="$(gh api "repos/$repository/pages" --jq .html_url 2>/dev/null || true)"
  if [[ -n "$page_url" ]]; then
    print "$page_url"
    exit 0
  fi
  sleep 2
done

print "GitHub Pages was configured for $repository/$branch; GitHub is still provisioning its URL."
exit 0
