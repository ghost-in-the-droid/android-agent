# Control Baby Name on Android with an AI agent

**Control Baby Name on Android with an AI agent.** Looking for a baby name? Tell your agent the gender and the letters, and it lists matching names with their origin.

Target search phrase: _AI agent finds baby names on Android_

Demo shows: `set_filter (gender=female, pattern=^Ma.+a$)`

> Ghost in the Droid seed skill for Baby Name (`fr.hnit.babyname`), an offline first name finder with about 46000 names. The gender radios, the regular expression field, the match counter and the name view are all text nodes, so an agent can search and browse. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_filter` | Restart the app and open the New Baby preferences form; return the live name count. | none |
| `set_filter` | Search names by gender (male, female, neutral, all) and a regular expression such as ^Ma.+a$, save the search and return the match count and the first name. | `gender`, `pattern` |
| `get_name` | Read the name on screen with its gender, origin and position (i of N). | none |
| `next_name` | Go to the next matching name and return it. | none |
| `previous_name` | Go back to the previous matching name and return it. | none |
| `list_names` | Read the current name and the next ones (up to 20) with gender and origin. | `count` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_filter |
| Primitives | set_filter, next_name, previous_name |
| Read state | get_name, list_names |

## Install

The app: F-Droid, or `https://f-droid.org/packages/fr.hnit.babyname/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/baby-name
```

## Use

```bash
ghost skill run ghost/baby-name set_filter --param gender=female --param "pattern=^Ma.+a$" --device <serial>
```

```python
run_skill(name="ghost/baby-name", action="set_filter", params={"gender": "female", "pattern": "^Ma.+a$"})
# {"result": {"count": 359, "first": "Manrica", "details": "[Female] [Italy]"}}
```

Try asking: "Find female baby names that start with Ma and end with a, then list five of them with their origin."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Baby Name 204. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 204 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- A pattern that matches nothing raises an error instead of saving.
- REMOVE and the star rating are not driven.

### Popups and first-run screens handled

- The delete confirmation for old searches is answered YES by the skill.
