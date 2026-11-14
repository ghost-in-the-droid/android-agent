# Control Wikipedia on Android with an AI agent

Demo shows: `open_article (title=Ada_Lovelace)`

> Ghost in the Droid seed skill for the official Wikipedia app (`org.wikipedia`). No account.

| Action | What it does | Params |
|---|---|---|
| `search_articles` | Search and return titles with short descriptions | `query`, `limit` |
| `open_article` | Open an article and return title, description and lead paragraph | `title` |
| `get_featured_article` | Today's featured article from the Explore feed | none |
| `save_article` | Save an article to the on-device Saved list | `title` |

## Install

The app: F-Droid (`org.wikipedia`) or the Play Store. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/wikipedia
```

## Use

```bash
ghost skill run ghost/wikipedia open_article --param title=Ada_Lovelace --device emulator-5554
ghost skill run ghost/wikipedia search_articles --param query="black holes" --param limit=5 --device emulator-5554
```

```python
run_skill(name="ghost/wikipedia", action="get_featured_article")
# {"date": "Oct 05, 2026", "title": "White-headed fruit dove", "description": "Species of bird endemic to Solomon Islands", ...}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Wikipedia r/50606, en-US, fresh install (onboarding handled). Signed self-runs in `runs/`. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| r/50606-r-2026-09-09 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Onboarding 1/4
- Onboarding 2/4 privacy
- Onboarding 3/4 languages
- Onboarding 4/4 interests
- Onboarding 4/4 interests (scrolled)
- Search widget promo
- OS permission policy: {"deny_permissions": ["notifications"]}

### Other known failure modes

- Titles that redirect (e.g. `Turing`) open the target article; the title check then fails by design. Pass the canonical title.
- Very short stubs can have a lead under 40 characters.
