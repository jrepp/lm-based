#!/usr/bin/env bash
# pre-push guard: refuse to push to a branch whose pull request is already merged.
# GitHub squash-merges PRs, so commits pushed after the merge never reach main
# (three PR #10 fixes were lost this way). Open a new branch from origin/main instead.
set -uo pipefail

branch="${1:-$(git branch --show-current)}"
[ -n "$branch" ] || exit 0
command -v gh >/dev/null 2>&1 || exit 0

state="$(gh pr view "$branch" --json state --jq .state 2>/dev/null)" || exit 0
if [ "$state" = "MERGED" ]; then
  echo "error: the pull request for '$branch' is already merged; commits pushed now will not reach main." >&2
  echo "Start a new branch from origin/main and cherry-pick them: git switch -c <new-branch> origin/main" >&2
  echo "(bypass with: git push --no-verify)" >&2
  exit 1
fi
exit 0
