# calculator - SOFT skill (LLM-adaptable narrative)

**Package**: `org.fossify.math` (Fossify Calculator, GPL-3.0, from F-Droid)
**Historical device check**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, app 1.4.0, en-US.
**Skill class**: HARD. Offline, no account.

## Layout reference

Main screen: display `id/result`, keypad buttons `id/btn_0` to `id/btn_9`, `btn_plus`, `btn_minus`, `btn_multiply` (×), `btn_divide` (÷), `btn_power` (^), `btn_percent`, `btn_root`, `btn_decimal`, `btn_clear` (C; long-press clears all), `btn_equals`. Toolbar: content-desc `History`, `Unit converter`, `More options`.

The app evaluates **immediately, left to right**: `84-2×6` is `(84-2)×6 = 492`, not 72. Agents that need precedence must split the work.

Numbers may show thousands separators (`1,234`); readers strip commas.

## Actions

### `calculate(expression)`

Long-press C, tap one button per character of the expression, tap `=`, read `id/result`. Success: the display equals the left-to-right value of the expression (absolute tolerance max(1e-6, abs(expected) * 1e-6)).

### `read_result()`

Read `id/result` on the main screen as a number. The validator rereads `id/result` and requires its text and parsed numeric value to equal the returned display and value.

### `get_history()`

Tap `History`; a dialog lists `id/item_formula` and `id/item_result` pairs, newest first. Read them and leave the dialog open for validation. Only the entries visible in the dialog are returned. The validator rereads both row lists and requires exact equality with the returned lists, equal list lengths and the History dialog title. An empty history passes only when the open dialog has no rows. The next action closes the dialog during startup.

### `convert_units(category, value, from_unit, to_unit)`

Tap `Unit converter`, tap the category tile (`id/unit_label` text), then tap `id/top_unit_name` and pick the source unit from the popup (items read like `Fahrenheit (°F)`), same for `id/bottom_unit_name`. Long-press C, key the value (and `+/-` for negatives). Read `id/bottom_unit_text`. The validator rereads source/target unit names, input value, converted value and symbol from the device and compares them with the returned data. Both unit names and input must also match the request. This validates the device result; it does not independently recompute conversion mathematics.

## Failure modes

- A unit name that the app does not list fails with the list of offered units in the error.
- The keypad loop rejects unmapped characters after launch and clear, and can have tapped a prefix already. The validator accepts numeric expressions with `+ - * / ^` and multiplication/division aliases `x`, `×`, `÷`; `%` has a keypad mapping but is not accepted by the arithmetic validator.
- Arithmetic validation evaluates only the requested operator; a zero right operand is valid for addition, subtraction and multiplication. Actual division by zero still fails.
