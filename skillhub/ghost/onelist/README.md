# Control 1List on Android with an AI agent — keep to-do lists

**Control 1List on Android with an AI agent.** Keep lists on your phone: an agent creates lists, adds and removes items and reads them back.

Target search phrase: _AI agent manages shopping lists on Android_

Demo shows: `create_list (name=Groceries)`

> Ghost in the Droid seed skill for 1List (`com.lolo.io.onelist`), a minimalist offline list app. List tabs and items are plain text, so an agent can keep shopping and todo lists. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_lists` | Restart the app and read the list tabs and the items of the selected list. | none |
| `create_list` | Create a new list (it becomes the selected list). | `name` |
| `select_list` | Switch to a list by its name. | `name` |
| `add_item` | Add an item to the selected list. | `item` |
| `remove_item` | Delete an item from the selected list by its text. | `item` |
| `get_items` | Read the list tabs and the items of the selected list. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_lists |
| Primitives | create_list, select_list, add_item, remove_item |
| Read state | get_items |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.lolo.io.onelist/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/onelist
```

## Use

```bash
ghost skill run ghost/onelist add_item --param item=Milk --device <serial>
```

```python
run_skill(name="ghost/onelist", action="add_item", params={"item": "Milk"})
# {"result": {"item": "Milk", "state": {"lists": [...], "items": ["Milk"]}}}
```

Try asking: "Create a list called Groceries in 1List, add Milk and Eggs and tell me what is on it."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), 1List 22. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 22 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Plain ASCII text only.
- The skill cannot tell which list tab is selected; create_list and select_list select a list and later calls act on it.
- Removing an item that is not on the selected list fails and names the items that are.

### Popups and first-run screens handled

- None.
