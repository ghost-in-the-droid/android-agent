# Control Decisions on Android with an AI agent

**Control Decisions on Android with an AI agent.** Can't decide? Your agent lists the pros and cons with weights and the scale shows the verdict.

Target search phrase: _AI agent weighs pros and cons decision on Android_

Demo shows: `new_issue (title=Buy a new phone)`

> Ghost in the Droid seed skill for Decisions (`de.markusfisch.android.libra`), an offline pros and cons tool with a balance that tips as you add weighted arguments. Titles and argument chips are text nodes, so an agent can weigh a decision. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_issues` | Restart the app and read the list of saved issues. | none |
| `new_issue` | Create a new issue with a title, ready for arguments. | `title` |
| `add_argument` | Add an argument with a weight from -10 (against) to 10 (for) to the open issue and watch the scale tip. | `text`, `weight` |
| `get_issue` | Read the open issue: title and every argument with its side (pro, con or neutral). | none |
| `list_issues` | Go back to the issue list and read every saved issue with its age. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_issues, new_issue |
| Primitives | add_argument |
| Read state | get_issue, list_issues |

## Install

The app: F-Droid, or `https://f-droid.org/packages/de.markusfisch.android.libra/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/decisions
```

## Use

```bash
ghost skill run ghost/decisions add_argument --param "text=Cheaper" --param weight=5 --device <serial>
```

```python
run_skill(name="ghost/decisions", action="add_argument", params={"text": "Cheaper", "weight": 5})
# {"result": {"text": "Cheaper", "weight": 5, "side": "pro"}}
```

Try asking: "Start a pros and cons list called Buy a new phone, add the pro Cheaper with weight 5 and the con Worse camera with weight -4, then read back the list."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Decisions 25. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 25 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The verdict shown by the balance cannot be read back, only the sides of the arguments.
- Deleting an issue or an argument is not driven.

### Popups and first-run screens handled

- The rename dialog is confirmed by the skill.
