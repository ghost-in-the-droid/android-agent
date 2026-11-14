# Control Calculator on Android with an AI agent

Demo shows: `convert_units (category=Temperature, value=100, from_unit=Fahrenheit, to_unit=Celsius)`

> Ghost in the Droid seed skill for Fossify Calculator (`org.fossify.math`), a FOSS calculator from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `calculate` | Key in an expression, press =, return the result | `expression` |
| `read_result` | Return the number on the display | none |
| `get_history` | Return recent calculations from the History dialog | none |
| `convert_units` | Convert a value with the built-in unit converter | `category`, `value`, `from_unit`, `to_unit` |

Note: the app evaluates left to right (`84-2*6` gives 492).

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.fossify.math/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/calculator
```

## Use

```bash
ghost skill run ghost/calculator calculate --param expression="1234*5" --device emulator-5554
ghost skill run ghost/calculator convert_units --param category=Temperature --param value=100 \
  --param from_unit=Fahrenheit --param to_unit=Celsius --device emulator-5554
```

```python
run_skill(name="ghost/calculator", action="calculate", params={"expression": "100/8"})
# {"display": "12.5", "value": 12.5}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Fossify Calculator 1.4.0, en-US. Signed self-runs in `runs/`. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.4.0 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 14/14 | 2026-10-05 |

Android 13 was additionally replayed on a 720x1600 Samsung SM-A037F (300 dpi, en-GB) and a 1080x2400 emulator (420 dpi, en-US). See [the cross-device report](../../../docs/reports/samsung-failure-fixes.md) for measured outcomes and limitations; other profiles remain unverified.

Historical self-run artifacts are retained in `runs/`, but the current registry rejects the pre-digest evidence as `unbound-helper`. These old counts do not establish current-version passing coverage; fresh digest-bound signed runs are pending.

### Recorded failures

The historical runs above were green. Samsung failures and subsequent fixes are recorded in [the cross-device report](../../../docs/reports/samsung-failure-fixes.md).

### Popups and first-run screens handled

- None app-specific; Android permission dialogs go through the engine's OS popup layer.

### Other known failure modes

- A unit name that the app does not list fails with the list of offered units in the error.
- The keypad loop rejects unmapped characters after launch and clear, and can have tapped a prefix already. The validator accepts numeric expressions with `+ - * / ^` and multiplication/division aliases `x`, `×`, `÷`; `%` has a keypad mapping but is not accepted by the arithmetic validator.
- Arithmetic validation evaluates only the requested operator; zero right operands work for addition, subtraction and multiplication. Actual division by zero fails.

## Compatibility and validation

The manifest targets Android >=13 and Fossify Calculator >=1.4.0, with en-US and en-GB flows. Its authoring screen is 1080x2400 at 420 dpi; measured Samsung/emulator outcomes are in the cross-device report. `calculate` rereads the device display and compares the left-to-right result. `read_result` independently rereads the display; `get_history` leaves History open and rereads its visible rows; `convert_units` rereads input, output, both unit names and the symbol, comparing each with the returned data. Conversion also checks caller input/unit names; it does not independently recompute conversion mathematics.
