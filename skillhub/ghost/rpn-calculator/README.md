# Control RPNcalc on Android with an AI agent

**Control RPNcalc on Android with an AI agent.** Compute with reverse Polish notation: an agent evaluates an RPN expression or drives the stack key by key.

Target search phrase: _AI agent uses an RPN calculator on Android_

Demo shows: `type_number (value=12.5)`

> Ghost in the Droid seed skill for RPNcalc (`dev.pesic.rpncalc`), an offline RPN stack calculator. The keypad and the stack lines are in the accessibility tree, so an agent can compute exactly and read the stack. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_calc` | Restart the app and read the stack. | none |
| `clear_all` | Clear the entry and the whole stack. | none |
| `type_number` | Type a number into the X register (digits, a dot, a leading minus). Follow with enter before the next number. | `value` |
| `enter` | Press Enter: lifts the stack and leaves a copy of X that the next typed number overwrites. | none |
| `operate` | Apply an operator to the top of the stack: + - * / ^ % neg swap. | `op` |
| `evaluate` | Clear the stack and evaluate a whole RPN expression such as '3 4 + 2 *' (tokens separated by spaces; operators + - * / ^ neg). | `expression` |
| `get_stack` | Read the stack (top of stack first). | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_calc |
| Primitives | type_number, enter, operate, evaluate, clear_all |
| Read state | get_stack |

## Install

The app: F-Droid, or `https://f-droid.org/packages/dev.pesic.rpncalc/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/rpn-calculator
```

## Use

```bash
ghost skill run ghost/rpn-calculator evaluate --param expression="3 4 + 2 *" --device <serial>
```

```python
run_skill(name="ghost/rpn-calculator", action="evaluate", params={"expression": "3 4 + 2 *"})
# {"result": {"state": {"stack": ["14"], "top": "14"}}}
```

Try asking: "Evaluate 3 4 + 2 * on the RPN calculator and tell me the result."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), RPNcalc 9. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 9 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Between two numbers press enter (or use evaluate); after enter the stack shows the number twice until you type the next one.
- An operator with fewer than two numbers on the stack fails.
- Division by zero and very long results depend on the app's own error display.

### Popups and first-run screens handled

- None.
