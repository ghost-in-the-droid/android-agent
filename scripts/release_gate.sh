#!/usr/bin/env bash
# Release gate (G7): run inside the release checkout after the strip list was applied, before the release commit.
# Fails when any strip-list path is still staged, when a proton.me mailbox address is in the staged tree,
# or when scripts/privacy/scan_forbidden.py finds a forbidden pattern anywhere in the tree.
set -euo pipefail
STRIP_LIST="${1:-scripts/public-strip.txt}"
rc=0
KEEP="$(grep '^!' "$STRIP_LIST" | sed 's/^!//' || true)"
while IFS= read -r strip_path; do
  [[ -z "$strip_path" || "$strip_path" == \#* || "$strip_path" == \!* ]] && continue
  if [[ -n "$(git ls-files -- "$strip_path" | grep -vxF -f <(printf '%s\n' "$KEEP" ) || true)" ]]; then
    echo "release gate: strip-list path still staged: $strip_path" >&2
    rc=1
  fi
done < "$STRIP_LIST"
if git grep --cached -q -I -iE '[a-z0-9._%+-]+@proton\.me' -- . 2>/dev/null; then
  echo "release gate: a proton.me mailbox address is in the staged tree" >&2
  rc=1
fi
if ! python3 "$(dirname "$0")/privacy/scan_forbidden.py" >&2; then
  echo "release gate: scripts/privacy/scan_forbidden.py reported forbidden patterns" >&2
  rc=1
fi
exit $rc
