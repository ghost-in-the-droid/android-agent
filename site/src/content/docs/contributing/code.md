---
title: "📝 Code Guidelines"
description: PR process, code style, what makes a good PR, and what to avoid.
---

This page covers general contribution guidelines for code changes beyond skill additions.

## PR Process

1. **Fork** the repository
2. **Create a branch** (`feature/thing` or `fix/thing`)
3. **Make your changes**
4. **Run tests:** `python3 -m pytest tests/ -v --tb=short`
5. **Open a PR** with a clear description of what and why

## What Makes a Good PR

- **Small and focused** -- one feature or fix per PR
- **Tested** -- include test commands or evidence it works
- **Documented** -- update relevant docs if behavior changes
- **No unrelated changes** -- don't refactor surrounding code in the same PR

## Code Style

- **Python 3.10+** target
- Use type hints where helpful (not required everywhere)
- No linter enforced yet -- match the style of surrounding code
- Prefer simple, readable code over clever abstractions
- Keep functions focused -- one function, one job
- Use `logging` for debug/info output, `print` for user-facing CLI output

## What to Avoid

- **Don't add dependencies** without discussion (open an issue first)
- **Don't change the database schema** without a migration (auto-applied on startup)
- **Don't modify API response formats** -- the dashboard depends on them
- **Don't commit credentials** -- API keys, service accounts, personal data
- **Don't force-push** to shared branches

## Contribution Types

| Type | Difficulty | Example |
|------|-----------|---------|
| Report a bug | Easy | Open a GitHub issue with repro steps |
| Improve documentation | Easy | Fix typos, add examples, clarify guides |
| Add UI elements for a new app | Easy-Medium | Map resource IDs for WhatsApp |
| Write an Action | Medium | Add `send_message` for WhatsApp |
| Write a Workflow | Medium | Chain actions into `send_dm` |
| Build a complete Skill | Medium-Hard | Full app coverage with tests |
| Core framework contribution | Hard | Scheduler improvements, new Device methods |

## Reporting Bugs

Open a GitHub issue with:

1. **What happened** (actual behavior)
2. **What you expected** (expected behavior)
3. **Steps to reproduce**
4. **Device info** (phone model, Android version, app version)
5. **Logs** (relevant error output from `/tmp/sched_job_*.log` or server console)
6. **Screenshot** (if UI-related)

## Project Areas

| Area | Key Files | Complexity |
|------|-----------|-----------|
| Device control | `bots/common/adb.py` | Medium |
| Skill system | `skills/base.py`, `skills/tiktok/` | Medium |
| API server | `server.py` | High (4500 LoC) |
| Database | `db.py` | High (2000 LoC) |
| Dashboard | `static/dashboard.html` | High (400K monolith) |
| Scheduler | `server.py` (scheduler section) | High |
| Bot scripts | `bots/tiktok/*.py` | Medium |
| LLM agent | `agent/agent_core.py` | Medium |

## Getting Help

- Open a **GitHub Discussion** for questions
- Tag `@maintainers` for urgent issues
- Check the [Troubleshooting](/troubleshooting/) page for common issues

## Related

- [Development Setup](/contributing/setup/) -- install and verify
- [Adding Skills](/contributing/skills/) -- the highest-impact contribution
