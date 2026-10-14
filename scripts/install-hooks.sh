#!/usr/bin/env bash
# Install the native push guard; pre-commit only exposes one ref from a multi-ref push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
hook="$(git rev-parse --git-path hooks/pre-push)"
wrapper='#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/check-branch-not-merged.sh" "$@"'
if [ -e "$hook" ] && [ "$(cat "$hook")" != "$wrapper" ]; then
  echo "error: $hook already exists; preserve or remove it explicitly before installing." >&2
  exit 1
fi
pre-commit install --hook-type pre-commit
mkdir -p "$(dirname "$hook")"
printf '%s\n' "$wrapper" > "$hook"
chmod +x "$hook"
