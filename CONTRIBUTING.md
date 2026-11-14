# Contributing

Thanks for your interest in contributing! This guide covers how to get involved, whether you're fixing a bug, adding a skill for a new app, or improving docs.

---

## Ways to Contribute

| Type | Difficulty | Impact |
|------|-----------|--------|
| Report a bug | Easy | High |
| Improve documentation | Easy | High |
| Add UI elements for a new app | Easy-Medium | High |
| Write an Action for an existing app | Medium | High |
| Write a Workflow (multi-step) | Medium | High |
| Build a complete app Skill | Medium-Hard | Very High |
| Core framework contribution | Hard | Very High |

**The highest-impact contribution is adding skills for new apps.** Every new app skill makes the framework more useful for everyone.

---

## Development Setup

### Prerequisites

- Python 3.10+
- Android phone with USB debugging enabled (or Android emulator)
- ADB installed and on PATH (`adb devices` shows your device)

### Install

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd ghost-in-the-droid
pip install -e ".[all]"
```

### Verify

```bash
# Check ADB sees your device
adb devices

# Run tests (requires connected phone)
DEVICE=<your_serial> python3 -m pytest tests/ -v --tb=short

# Start the dashboard
python3 run.py
# Open http://localhost:5055
```

---

## Adding a Skill for a New App

Skills live in the Skill Hub at `skillhub/<your-github-login>/<slug>/`: a `skill.yaml` (Schema v2), a `README.md`, a `SOFT.md`, and optional `helpers.py`, `validators.py`, `bench.yaml` and `demo.gif`. You own your folder: once your first skill is merged, the generated `.github/CODEOWNERS` maps `skillhub/<your-login>/` to you and you review changes to it yourself.

```bash
ghost skill scaffold <you>/<slug> --app <package> --actions <action>
# author skill.yaml, README.md, SOFT.md; set license: and generated_with:
ghost skill validate <path>
ghost skill lint <path>
ghost skill run <path> <action> --record   # signed self-run in runs/
ghost skill submit <path> --dry-run        # prints the PR plan; automated PR creation is v1.7, open the PR by hand
```

Then file a **Verify request** issue so someone with a different phone can run it. Your skill climbs Draft, Runs, Proven, Hardened, Reference on evidence from real runs; downloads and likes are worth zero points.

You can also contribute without writing a skill: verify other people's skills on your phones (`ghost skill verify <author>/<slug>`), review them, or answer questions. All four tracks lead to the same contributor tiers.

- How the ladder works: [`docs/community/contributor-ladder.md`](docs/community/contributor-ladder.md)
- Full author flow and CI: [`docs/contributing-skills.md`](docs/contributing-skills.md)
- Schema reference: [`docs/skill-schema-v2.md`](docs/skill-schema-v2.md)
- Wanted skills: [open skill requests](https://github.com/ghost-in-the-droid/android-agent/issues?q=is%3Aopen+label%3Awanted-skill)

Ground rules: personal-account actions only, no engagement farming, mass messaging or scraping other people's data, declare `data_access:` and `side_effects:` honestly, and say in `generated_with:` if AI helped.

---

## Code Contributions

### Backend Architecture

The server is **FastAPI + SQLAlchemy 2.0 + Pydantic v2**:

```
gitd/
  app.py              # FastAPI app factory + router registration
  config.py           # Pydantic settings from .env
  models/             # SQLAlchemy 2.0 ORM (11 tables)
  schemas/            # Pydantic v2 request/response models
  routers/            # FastAPI route handlers (14 routers)
  services/           # Business logic + shared helpers
  alembic/            # Database migrations
```

- Use `db: Session = Depends(get_db)` for database access in routes
- Use `sqlalchemy.text()` for complex SQL, ORM for simple CRUD
- Run `alembic revision --autogenerate -m "desc"` after model changes
- Auto-generated API docs at `http://localhost:5055/docs`

### Code Style

- Python 3.10+ with type hints
- Lint with `ruff check gitd/`
- Format with `ruff format gitd/`
- Prefer simple, readable code over clever abstractions
- Keep functions focused — one function, one job

### PR Process

1. Fork the repo
2. Create a branch (`feature/thing` or `fix/thing`)
3. Make your changes
4. Run tests: `python3 -m pytest tests/ -v --tb=short`
5. Open a PR with a clear description of what and why

### What Makes a Good PR

- **Small and focused** — one feature or fix per PR
- **Tested** — include test commands or evidence it works
- **Documented** — update relevant docs if behavior changes
- **No unrelated changes** — don't refactor surrounding code

### What to Avoid

- Don't add dependencies without discussion
- Don't change the database schema without a migration
- Don't modify API response formats (breaks dashboard)
- Don't commit API keys, credentials, or personal data

---

## Reporting Bugs

Open a GitHub issue with:

1. **What happened** (actual behavior)
2. **What you expected** (expected behavior)
3. **Steps to reproduce**
4. **Device info** (phone model, Android version, app version)
5. **Logs** (relevant error output)
6. **Screenshot** (if UI-related)

---

## Questions?

- Open a GitHub Discussion for questions
- Join our [Discord](https://discord.gg/gmvDX4Juk) for real-time help
- Tag `@maintainers` for urgent issues
