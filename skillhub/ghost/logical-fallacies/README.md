# Control Logical Defence on Android with an AI agent — look up logical fallacies

**Control Logical Defence on Android with an AI agent.** Look up logical fallacies on your phone: an agent lists them, reads definitions and examples and groups them by category.

Target search phrase: _AI agent explains logical fallacies on Android_

Demo shows: `list_fallacies (category=On the Attack, limit=5)`

> Ghost in the Droid seed skill for Logical Defence (`za.co.lukestonehm.logicaldefence`), an offline encyclopedia of logical fallacies. Every entry (number, name, definition, example) is readable text, so an agent can look fallacies up and explain them. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `list_categories` | List the fallacy categories from the navigation drawer. | none |
| `list_fallacies` | List the fallacies of a category (number and name); without a category the one on screen. | `category`, `limit` |
| `get_fallacy` | Read one fallacy by its exact name from any category: number, category, definition and example. | `name` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | list_categories |
| Primitives | list_fallacies |
| Read state | get_fallacy |

## Install

The app: F-Droid, or `https://f-droid.org/packages/za.co.lukestonehm.logicaldefence/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/logical-fallacies
```

## Use

```bash
ghost skill run ghost/logical-fallacies list_fallacies --param 'category=On the Attack' --device <serial>
ghost skill run ghost/logical-fallacies get_fallacy --param 'name=Appeal to Authority' --device <serial>
```

```python
run_skill(name="ghost/logical-fallacies", action="get_fallacy", params={"name": "Appeal to Authority"})
# {"result": {"fallacy": {"number": 2, "definition": "...", "example": "..."}}}
```

Try asking: "List the categories of logical fallacies and explain Appeal to Authority."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Logical Defence 25. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 25 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- get_fallacy needs the exact name; an unknown name fails after walking every category.
- get_fallacy can take about a minute when the fallacy is in a later category.
- The example text is the last line of the entry description and may be empty.

### Popups and first-run screens handled

- None.
