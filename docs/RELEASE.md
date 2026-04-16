# Release Process

How we cut a new release of Ghost in the Droid and publish it to GitHub + PyPI.

---

## Versioning — Semantic (SemVer)

`MAJOR.MINOR.PATCH`

- **MAJOR** — breaking changes (DB schema incompatible, API removed, skill framework rewrite)
- **MINOR** — new features, backwards compatible (new provider, new skill, new tab)
- **PATCH** — bug fixes only, no new features

Examples: `1.0.0 → 1.1.0` (Ollama added), `1.1.0 → 1.1.1` (fix parse bug), `1.1.0 → 2.0.0` (skills YAML format changes).

---

## Repo Flow

```
   private-mirror (work here)
        │
        │ open PR against private-mirror/main
        ▼
   private-mirror/main  ← first merge here; CI runs
        │
        │ sync main → feature branch on public
        ▼
   public/android-agent (release target)
        │
        │ tag vX.Y.Z on public main
        ▼
   [publish.yml fires]
        │
        ├─► PyPI: ghost-in-the-droid==X.Y.Z
        │
        └─► GitHub Release: v X.Y.Z with notes
```

**Never push directly to public `main`.** Always go through private mirror PR → public PR → tag.

---

## Release Checklist

### 1. Land all features on private mirror `main`

- All PRs merged, CI green
- Manual smoke test: `python3 run.py` starts, dashboard loads, one end-to-end flow works (e.g. take screenshot on a real device)

### 2. Bump version + update changelog

On private-mirror `main`:

```bash
# Update pyproject.toml
sed -i 's/^version = "1.0.0"/version = "1.1.0"/' pyproject.toml

# Move [Unreleased] → [1.1.0] — YYYY-MM-DD in CHANGELOG.md
# Add the compare link at the bottom
```

Commit message: `Bump version to X.Y.Z`

### 3. Create release PR on public repo

```bash
# Push private mirror/main as a feature branch on public
git remote add public https://github.com/ghost-in-the-droid/android-agent.git
git fetch public main
git push public origin/main:refs/heads/release/vX.Y.Z

# Open PR
gh pr create --repo ghost-in-the-droid/android-agent \
  --base main --head release/vX.Y.Z \
  --title "Release vX.Y.Z" \
  --body-file CHANGELOG_SECTION.md
```

Wait for CI to pass on public. Review. Merge.

### 4. Tag the release

```bash
# On the merged public main
git checkout main && git pull public main
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push public vX.Y.Z
```

This triggers `.github/workflows/publish.yml`:
- Builds the package (`python -m build`)
- Verifies entry points (`android-agent --help`, MCP import)
- Publishes to PyPI via `PYPI_PROJECT_TOKEN`

### 5. Create GitHub Release

```bash
gh release create vX.Y.Z \
  --repo ghost-in-the-droid/android-agent \
  --title "vX.Y.Z" \
  --notes-file CHANGELOG_SECTION.md \
  --latest
```

(Or via the GitHub UI: Releases → Draft a new release → pick tag `vX.Y.Z` → paste changelog section.)

### 6. Verify

```bash
# Clean environment
uvx --from ghost-in-the-droid==X.Y.Z android-agent-mcp --help

# PyPI page
open https://pypi.org/project/ghost-in-the-droid/X.Y.Z/

# GitHub release page
open https://github.com/ghost-in-the-droid/android-agent/releases/tag/vX.Y.Z
```

---

## What's Automated vs Manual

| Step | Automated | Manual |
|------|-----------|--------|
| CI (lint, test, type-check, frontend build) | ✅ on every PR | — |
| PyPI publish | ✅ on `v*` tag push | push the tag |
| Package verification (install + entry points) | ✅ in publish.yml | — |
| GitHub Release | ⚠️ partial (can be scripted below) | click "Publish release" |
| CHANGELOG.md | ❌ | write release notes |
| Version bump | ❌ | `sed` command |
| Private → Public sync | ❌ | push branch + PR |

---

## GitHub Secrets (already configured)

| Secret | Where used | Purpose |
|--------|-----------|---------|
| `PYPI_PROJECT_TOKEN` | `publish.yml` | PyPI upload (project-scoped token) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` | `ci.yml` | Integration tests (optional) |

---

## Automation Roadmap

Full automation would reduce manual steps to: **write CHANGELOG entry → click a button**.

### Phase 1 (easy wins)
- [ ] Add a `release.sh` script that does: version bump + CHANGELOG stamp (move `[Unreleased]` → `[X.Y.Z]` with today's date) + commit + tag + push
- [ ] Add auto-create GitHub Release in `publish.yml` (use `softprops/action-gh-release@v2` after PyPI upload, pulls notes from CHANGELOG.md section)
- [ ] Pre-commit hook that runs `ruff check` + secret-scan (detect-secrets or gitleaks) on every commit

### Phase 2 (medium effort)
- [ ] `release-please` bot — reads conventional commits, auto-generates changelog + opens release PR on every merge to main
- [ ] Branch protection on public `main`: require PR, require CI green, require 1 review, no force push
- [ ] Dependabot for pip + npm

### Phase 3 (nice to have)
- [ ] Trusted Publishing to PyPI (OIDC, no stored token)
- [ ] Sigstore attestations on releases (supply chain security)
- [ ] Multi-package support if we split `gitd` into `gitd-core` + `gitd-cli` + `gitd-mcp`
- [ ] Matrix CI: Python 3.10/3.11/3.12 × ubuntu/macos × latest/minimum deps

---

## Hotfix Process

For urgent fixes on a released version:

```bash
# Branch from the tag
git checkout -b hotfix/1.1.1 v1.1.0

# Apply fix, commit
...

# Bump PATCH version, update CHANGELOG
sed -i 's/version = "1.1.0"/version = "1.1.1"/' pyproject.toml

# Push, PR to private-mirror/main, then public/main, then tag v1.1.1
```

Same flow as a regular release, just smaller scope.

---

## Rollback

If a release is broken:

**PyPI** — you can't delete a version, but you can yank it (prevents installs without explicit pin):

```bash
pip install twine
twine upload --repository pypi dist/* --skip-existing
# Go to https://pypi.org/manage/project/ghost-in-the-droid/ → Yank
```

**GitHub Release** — delete via UI or `gh release delete vX.Y.Z --yes`.

**Tag** — `git push --delete public vX.Y.Z` (leaves PyPI version yanked).

Then cut a new PATCH release with the fix.

---

## Release Cadence

No fixed cadence. Release whenever:
- A meaningful feature lands (MINOR)
- A user-visible bug is fixed (PATCH)
- Accumulated ~2-4 PRs on main

Don't batch fixes if they're blocking users. Don't release daily — cut noise.
