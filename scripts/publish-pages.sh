#!/bin/zsh
# Publish the contents of site/ to a separate GitHub Pages branch without
# switching the developer's working branch or committing local observation data.
set -euo pipefail

script_dir="${0:A:h}"
repo_root="$(git -C "$script_dir/.." rev-parse --show-toplevel)"
source_dir="${1:-$repo_root/site}"
remote="${WAITWATCH_PAGES_REMOTE:-origin}"
branch="${WAITWATCH_PAGES_BRANCH:-gh-pages}"

if [[ ! -f "$source_dir/index.html" ]]; then
  print -u2 "Pages source does not contain index.html: $source_dir"
  exit 1
fi

worktree="$(mktemp -d "${TMPDIR:-/tmp}/restowaitlist-pages.XXXXXX")"
rmdir "$worktree"
cleanup() {
  git -C "$repo_root" worktree remove --force "$worktree" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! git -C "$repo_root" fetch "$remote" "$branch" --quiet 2>/dev/null; then
  print "Creating the $branch branch from the local static site."
fi

if git -C "$repo_root" show-ref --verify --quiet "refs/remotes/$remote/$branch"; then
  git -C "$repo_root" worktree add --detach "$worktree" "$remote/$branch" --quiet
else
  git -C "$repo_root" worktree add --detach "$worktree" HEAD --quiet
  git -C "$worktree" switch --orphan "$branch" --quiet
  # An orphan checkout may already have an empty index; rsync below clears
  # any remaining working files before adding the static site.
  git -C "$worktree" rm -r --force . >/dev/null 2>&1 || true
fi

rsync -a --delete --exclude '.git' "$source_dir/" "$worktree/"
git -C "$worktree" add --all
# The source checkout intentionally ignores the live export. On gh-pages it is
# public content, so stage that one generated file explicitly.
if [[ -f "$worktree/data/waits.json" ]]; then
  git -C "$worktree" add --force data/waits.json
fi
if git -C "$worktree" diff --cached --quiet; then
  print "GitHub Pages is already current."
  exit 0
fi

if [[ "${WAITWATCH_PAGES_DRY_RUN:-0}" == "1" ]]; then
  print "Dry run: GitHub Pages would be updated."
  exit 0
fi

git -C "$worktree" commit -m "Publish wait table" --quiet
git -C "$worktree" push "$remote" "HEAD:$branch" --quiet
print "Published static table to $remote/$branch."
