# Release Process

How we cut a new release of Ghost in the Droid and publish it to GitHub + PyPI.

**TL;DR:** `./scripts/release.sh 1.3.0` → merge the PR it opens → `git tag v1.3.0 && git push public v1.3.0` → done. Workflows handle PyPI + GitHub Release + archive sync automatically.

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
   private-mirror (dev target)
        │
        │ feature PRs land on main
        ▼
   private-mirror/main  ← release.sh runs here
        │
        │ script creates clean PR on public (rebuilt on public/main)
        ▼
   public/main ← merge PR
        │
        │ push v* tag
        ▼
   [publish.yml fires automatically]
        │
        ├─► PyPI: ghost-in-the-droid==X.Y.Z
        ├─► GitHub Release v X.Y.Z with CHANGELOG notes
        └─► Archive: mirror public/main + tag to android-agent-archive
```

**Never push directly to public `main`.** Always go through the release.sh flow.

---

## Quick Release (automated path)

### 1. Run the script on private-mirror/main

```bash
./scripts/release.sh 1.3.0
```

This does everything up to opening the public PR:
- Pulls latest private-mirror/main
- Bumps `pyproject.toml` version
- Stamps CHANGELOG.md (moves `[Unreleased]` → dated section, updates compare links)
- Commits + pushes to private-mirror/main
- Creates `release/v1.3.0` branch on public (rebuilt on top of public/main — no history-divergence conflicts)
- Opens PR on public with CHANGELOG notes as the body

### 2. Wait for CI + merge the public PR

4 checks on public (lint, test, type-check, build-frontend) — all must pass.

Use **Squash and merge** on the public repo.

### 3. Tag

```bash
git fetch public
git checkout public/main
git tag v1.3.0
git push public v1.3.0
```

### 4. Automation takes over

The tag push triggers `.github/workflows/publish.yml` which:
- Builds the package, verifies entry points
- Publishes to PyPI (`PYPI_PROJECT_TOKEN`)
- Creates the GitHub Release with notes pulled from CHANGELOG.md
- Mirrors `public/main` + the tag to the archive repo (needs `ARCHIVE_PUSH_TOKEN` secret)

### 5. Verify

```bash
pip install ghost-in-the-droid==1.3.0
# GitHub release: https://github.com/ghost-in-the-droid/android-agent/releases/tag/v1.3.0
# PyPI: https://pypi.org/project/ghost-in-the-droid/1.3.0/
```

---

## Manual Path (if the script fails)

Everything release.sh does can be done by hand; see git history for worked examples (v1.0.0, v1.1.0, v1.2.0).

The one thing that's easy to miss: when pushing private-mirror/main to public, history often diverges (private-mirror has non-squashed PR merges, public is squashed). Fix: rebuild a clean release branch on top of public/main:

```bash
git fetch public
git checkout -B release/vX.Y.Z public/main
# Apply cumulative diff from the last "Release" commit on main onto public/main:
git diff <last-release-commit>..main | git apply --3way --index
git commit -m "Release vX.Y.Z"
git push public release/vX.Y.Z
gh pr create --repo ghost-in-the-droid/android-agent --base main --head release/vX.Y.Z ...
```

The script automates this pattern.

---

## GitHub Secrets (one-time setup)

| Secret | Repo | Purpose |
|--------|------|---------|
| `PYPI_PROJECT_TOKEN` | `android-agent` (public) | PyPI upload via `publish.yml` |
| `ARCHIVE_PUSH_TOKEN` | `android-agent` (public) | Auto-mirror to archive repo. PAT with `repo` scope on `android-agent-archive`. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` | all repos | Integration tests (optional) |

Set in **Settings → Secrets and variables → Actions** on each repo.

---

## What's Automated

| Step | Automated | Manual |
|------|-----------|--------|
| CI (lint, test, type-check, frontend build) on every PR | ✅ | — |
| Version bump + CHANGELOG stamp | ✅ (release.sh) | — |
| Release PR on public | ✅ (release.sh) | — |
| PyPI publish | ✅ (publish.yml on tag) | push the tag |
| Package verification (install + entry points) | ✅ (publish.yml) | — |
| GitHub Release creation | ✅ (publish.yml on tag) | — |
| Archive mirror sync | ✅ (mirror-to-archive.yml on tag) | — |

---

## Still Manual (see "Automation Roadmap" section)

- CHANGELOG entry for each PR — currently human-written. Could be auto-generated from conventional-commit messages via `release-please` bot.
- Merging release PRs on public — intentionally manual (human review gate before shipping).
- Deciding when to cut a release — by user request, not time-based.

---

## Hotfix Process

Urgent fix on a released version:

```bash
# Branch from the tag
git checkout -b hotfix/1.1.1 v1.1.0
# Apply fix
...
# Use release.sh with the PATCH-bumped version
./scripts/release.sh 1.1.1
```

Same flow as a regular release, just smaller scope.

---

## Rollback

**PyPI** can't be deleted, only yanked:
- Go to https://pypi.org/manage/project/ghost-in-the-droid/ → Yank

**GitHub Release** — `gh release delete vX.Y.Z --yes`

**Tag** — `git push --delete public vX.Y.Z`

Then cut a new PATCH release with the fix.

---

## Automation Roadmap

See [`mono/docs/refactor/release-automation-nbs.md`](https://github.com/ghost-in-the-droid/mono/blob/main/docs/refactor/release-automation-nbs.md) for the next-level automation plans that are deliberately not shipped yet (release-please bot, squash-merge enforcement, Trusted Publishing, public-first workflow).
