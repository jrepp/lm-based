#!/usr/bin/env bash
# Native pre-push hook: inspect every destination ref, including explicit refspecs.
set -uo pipefail

remote_url="${2:-}"
[ -n "$remote_url" ] || exit 0
command -v gh >/dev/null 2>&1 || exit 0

# Resolve through gh so SSH aliases and fork remotes use the actual destination.
repo="$(gh repo view "$remote_url" --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" || exit 0
status=0
while read -r local_ref local_sha remote_ref remote_sha; do
  case "$local_sha" in ''|0000000000000000000000000000000000000000) continue ;; esac
  case "$remote_ref" in refs/heads/*) branch="${remote_ref#refs/heads/}" ;; *) continue ;; esac
  state="$(gh pr view "$branch" --repo "$repo" --json state --jq .state 2>/dev/null)" || continue
  if [ "$state" = "MERGED" ]; then
    echo "error: the pull request for '$repo:$branch' is already merged; this push will not update it." >&2
    echo "Create a new branch and pull request for these commits (bypass: git push --no-verify)." >&2
    status=1
  fi
done
exit "$status"
