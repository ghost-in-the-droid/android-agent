# Control Shopping List on Android with an AI agent

**Control Shopping List on Android with an AI agent.** Add items to your shopping list, tick them off and clear the bought ones from your phone by asking an agent.

Target search phrase: _AI agent shopping list Android_

Demo shows: `add_item (name=Milk, quantity=2)`

> Ghost in the Droid seed skill for Shopping List (`com.woefe.shoppinglist`), a FOSS offline shopping list from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `add_item` | Add one item with an optional quantity | `name`, `quantity` |
| `add_items` | Add several comma separated items | `items` |
| `get_items` | Return every item with its quantity | none |
| `check_item` | Toggle an item's checked (grey) state by tapping its row | `name` |
| `remove_checked` | Delete all checked items (needs confirm=yes) | `confirm` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | add_item |
| Primitives | add_items, check_item, remove_checked |
| Read state | get_items |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.woefe.shoppinglist/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/shopping-list
```

## Use

```bash
ghost skill run ghost/shopping-list add_item --param name=Milk --param quantity=2 --device <serial>
ghost skill run ghost/shopping-list get_items --device <serial>
```

```python
run_skill(name="ghost/shopping-list", action="get_items")
# {"items": [{"name": "Milk", "quantity": "2"}]}
```

Try asking: "Add milk, eggs and bread to my shopping list."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Shopping List 0.11.0. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 0.11.0 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The add panel stays open between runs: `get_items` presses BACK until the add button is visible.
- Quantity is passed as text; digits from CLI callers arrive as ints, the helper stringifies them.
- Checked (grey) items are not read back: the app does not expose the state.

### Popups and first-run screens handled

- None: the app has no first-run screens and asks for no permissions.
