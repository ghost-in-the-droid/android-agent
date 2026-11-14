# Control Daily Diary on Android with an AI agent

**Control Daily Diary on Android with an AI agent.** Dictate a diary line to your agent: it writes today's entry in Daily Diary and reads it back later.

Target search phrase: _AI agent writes a diary entry on Android_

Demo shows: `write_entry (text=Walked in the park and read a book)`

> Ghost in the Droid seed skill for Daily Diary (`com.voklen.daily_diary`), an offline one-page-per-day diary. Today's entry is a single text field that autosaves, so an agent can write, append and read it. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_diary` | Restart the app and read today's entry. | none |
| `write_entry` | Replace today's diary entry with the given text. | `text` |
| `append_entry` | Add text to the end of today's diary entry. | `text` |
| `read_entry` | Read today's diary entry. | none |
| `list_previous` | Open the previous-entries screen, return its rows and come back. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_diary |
| Primitives | write_entry, append_entry, list_previous |
| Read state | read_entry |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.voklen.daily_diary/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/daily-diary
```

## Use

```bash
ghost skill run ghost/daily-diary write_entry --param text='A calm day' --device <serial>
```

```python
run_skill(name="ghost/daily-diary", action="write_entry", params={"text": "A calm day"})
```

Try asking: "Write in my Daily Diary: Walked in the park and read a book. Then read it back to me."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Daily Diary 17. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 17 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- write_entry replaces the whole entry; use append_entry to add.
- Older days only exist after the app has been used on earlier dates.

### Popups and first-run screens handled

- None.
