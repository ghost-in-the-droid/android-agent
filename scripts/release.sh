#!/usr/bin/env bash
# release.sh — cut a new release from private-mirror/main.
#
# Does: version bump, CHANGELOG stamp (move [Unreleased] → dated section,
# update compare links), commit, push to private-mirror/main, create a
# clean release PR on public repo (rebuilt on top of public/main to avoid
# history-divergence conflicts).
#
# Usage:
#   ./scripts/release.sh 1.3.0
#
# After merge of the public PR, tag on public main:
#   git tag v1.3.0 && git push public v1.3.0
# → triggers publish.yml → PyPI + GitHub Release + archive sync (all automated)
set -euo pipefail

NEW_VERSION="${1:-}"
if [[ -z "$NEW_VERSION" ]]; then
  echo "Usage: $0 <version>   e.g.  $0 1.3.0" >&2
  exit 1
fi

if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must match X.Y.Z (got '$NEW_VERSION')" >&2
  exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
  echo "Error: must be on main (currently on $BRANCH)" >&2
  exit 1
fi

if ! git diff-index --quiet HEAD --; then
  echo "Error: working tree not clean" >&2
  exit 1
fi

# Ensure public remote exists
if ! git remote get-url public >/dev/null 2>&1; then
  git remote add public https://github.com/ghost-in-the-droid/android-agent.git
fi

echo "→ Pulling latest main"
git pull --ff-only origin main
git fetch public main

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed -E 's/^version = "(.+)"/\1/')
TODAY=$(date +%Y-%m-%d)

echo "→ Bumping $CURRENT_VERSION → $NEW_VERSION"
sed -i.bak "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
rm pyproject.toml.bak

echo "→ Stamping CHANGELOG.md"
python3 - "$NEW_VERSION" "$CURRENT_VERSION" "$TODAY" <<'PY'
import re, sys
new, old, today = sys.argv[1], sys.argv[2], sys.argv[3]
with open("CHANGELOG.md") as f:
    c = f.read()

# Insert dated section below [Unreleased]
c = c.replace(
    "## [Unreleased]\n",
    f"## [Unreleased]\n\n## [{new}] — {today}\n",
    1,
)

# Update [Unreleased] compare link (was v{old}...HEAD, now v{new}...HEAD)
c = re.sub(
    r"^\[Unreleased\]:.*$",
    f"[Unreleased]: https://github.com/ghost-in-the-droid/android-agent/compare/v{new}...HEAD",
    c,
    flags=re.MULTILINE,
)

# Add the new version's compare link just under [Unreleased]
new_link = f"[{new}]: https://github.com/ghost-in-the-droid/android-agent/compare/v{old}...v{new}"
c = re.sub(
    r"^(\[Unreleased\]:.*\n)",
    rf"\1{new_link}\n",
    c,
    count=1,
    flags=re.MULTILINE,
)

with open("CHANGELOG.md", "w") as f:
    f.write(c)
PY

echo "→ Committing version bump on private-mirror/main"
git add pyproject.toml CHANGELOG.md
git commit -m "Release v$NEW_VERSION"
git push origin main

# Build clean release branch on top of public/main
echo "→ Creating release/v$NEW_VERSION on public from public/main"
RELEASE_BRANCH="release/v$NEW_VERSION"
git checkout -B "$RELEASE_BRANCH" public/main

# Determine the commit on private-mirror that the previous tag was cut from
# by looking for the most recent "Release v" commit before this one.
LAST_RELEASE_COMMIT=$(git log main --grep="^Release v" --format="%H" | sed -n '2p')
if [[ -z "$LAST_RELEASE_COMMIT" ]]; then
  echo "Error: couldn't find previous 'Release v' commit on main" >&2
  exit 1
fi

echo "→ Applying cumulative diff from $LAST_RELEASE_COMMIT..main onto public/main"
git diff "$LAST_RELEASE_COMMIT..main" | git apply --3way --index || {
  echo "→ 3-way apply had issues, trying direct apply"
  git diff "$LAST_RELEASE_COMMIT..main" | git apply --index
}

git commit -m "Release v$NEW_VERSION"
git push public "$RELEASE_BRANCH"

# Extract the [new version] section from CHANGELOG for PR body
PR_BODY=$(python3 - "$NEW_VERSION" <<'PY'
import re, sys
new = sys.argv[1]
with open("CHANGELOG.md") as f:
    c = f.read()
m = re.search(rf"## \[{re.escape(new)}\].*?(?=\n## |\Z)", c, re.DOTALL)
if m:
    body = m.group(0)
else:
    body = f"Release v{new}"
print(body)
PY
)

echo "→ Opening PR on public repo"
gh pr create \
  --repo ghost-in-the-droid/android-agent \
  --base main --head "$RELEASE_BRANCH" \
  --title "Release v$NEW_VERSION" \
  --body "$PR_BODY

---

After CI green + merge: tag \`v$NEW_VERSION\` on public main to trigger PyPI publish + GitHub Release + archive sync."

# Restore private-mirror working copy
git checkout main

echo ""
echo "✓ v$NEW_VERSION release PR opened on public repo"
echo ""
echo "Next steps (after CI green):"
echo "  1. Review/merge the public PR"
echo "  2. Tag on public main:"
echo "       git fetch public && git checkout public/main"
echo "       git tag v$NEW_VERSION && git push public v$NEW_VERSION"
echo "  3. Workflows handle the rest: PyPI, GitHub Release, archive sync"
