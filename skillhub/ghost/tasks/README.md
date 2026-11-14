# Control Tasks on Android with an AI agent — manage to-do lists

Demo shows: `add_task (title=Water the plants)`

> Ghost in the Droid seed skill for Tasks.org (`org.tasks`), a FOSS to-do app from F-Droid. Local lists only: no account, no sync.

| Action | What it does | Params |
|---|---|---|
| `add_task` | New task in the default local list | `title`, `notes` |
| `list_tasks` | Open tasks with notes and section | none |
| `search_tasks` | Tasks matching a text | `query` |
| `complete_task` | Tick a task by exact title | `title` |

## Install

Install the app from F-Droid (`org.tasks`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/tasks
```

## Use

```bash
ghost skill run ghost/tasks add_task --param "title=Buy stamps" --device emulator-5554
ghost skill run ghost/tasks complete_task --param "title=Buy stamps" --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/tasks", action="list_tasks")
# {"tasks": [{"title": "Call the bank", "notes": "about the card", "section": "No due date"}], "count": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Tasks.org 15.12, en-US. Signed self-runs live in `runs/`.

## Notes

The editor's Save button is in the top toolbar; the skill taps it only when no heads-up notification is showing. Tasks are never deleted. License: MIT (the skill; the app is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 15.12 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Android 13 was additionally replayed on a 720x1600 Samsung SM-A037F (300 dpi, en-GB) and a 1080x2400 emulator (420 dpi, en-US). See [the cross-device report](../../../docs/reports/samsung-failure-fixes.md) for measured outcomes and limitations; other profiles remain unverified.

### Recorded failures

The historical runs above were green. Samsung failures and subsequent fixes are recorded in [the cross-device report](../../../docs/reports/samsung-failure-fixes.md).

### Popups and first-run screens handled

- First-run account choice (local lists)
- Enable-reminders banner
- Notification permission prompt

### Other known failure modes

- With "show completed" on, completed tasks stay visible with a strike-through; `complete_task` would then need a checked-state check.
- Duplicate titles: `complete_task` ticks the first match.

On OEMs without the AOSP pinned-notification field, toolbar taps require Tasks focus and an independently unobscured target. Compose controls additionally use the focused window bounds and every higher visible window; unknown geometry or an overlap refuses the tap.
