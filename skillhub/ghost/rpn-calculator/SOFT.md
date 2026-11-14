# rpn-calculator - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `dev.pesic.rpncalc` (RPNcalc, GPL-3.0-only, version 9 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Stack lines: views with the value as content-desc, the lowest line is X (top of stack).
- Keys: Swap, R up/down, undo, C or AC, plus/minus, y^x, %, digits, dot, Backspace, divide, multiply, minus, plus, Enter.
- Enter lifts the stack and leaves a copy of X; the next typed number overwrites that copy (HP style).

## Actions

### `open_calc()`

Force-stops and relaunches.

### `clear_all()`

Taps C (entry) and then AC (stack).

### `type_number(value)`

Taps the digit keys and the plus/minus key for a negative number.

### `enter()`

Taps Enter.

### `operate(op)`

Taps the operator; with two numbers it replaces them by the result (Y op X).

### `evaluate(expression)`

Types each number, presses Enter only between two numbers and applies each operator. The expected result is computed in Python and compared with the stack top.

### `get_stack()`

Reads the stack lines (content-desc views) above the keypad.

## Adapting

The two roll keys (R up/down) and the undo key are not driven (they have no usable label); the stack view shows only the last lines, so very deep stacks are truncated.
