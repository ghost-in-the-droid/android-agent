# Control Qonvert on Android with an AI agent

**Control Qonvert on Android with an AI agent.** Convert numbers between binary, octal, decimal, duodecimal and hexadecimal: an agent types the number and reads every representation.

Target search phrase: _AI agent converts numbers between bases on Android_

Demo shows: `convert (value=255, from_base=10, to_base=16)`

> Ghost in the Droid seed skill for Qonvert (`org.tessoft.qonvert`), an offline number converter for positional bases. The input, the bases and all outputs are plain text, so an agent can convert exactly and read fractions and Roman numerals. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_converter` | Restart the app and read the converter. | none |
| `convert` | Convert a number from one base to another and return every representation shown (value in the output base, fraction, mixed number, continued fractions, Roman numerals for integers). | `value`, `from_base`, `to_base` |
| `get_result` | Read the current input, the bases and all output representations. | none |
| `clear_input` | Clear the input field. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_converter |
| Primitives | convert, clear_input |
| Read state | get_result |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.tessoft.qonvert/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/qonvert
```

## Use

```bash
ghost skill run ghost/qonvert convert --param value=255 --param to_base=hex --device <serial>
```

```python
run_skill(name="ghost/qonvert", action="convert", params={"value": "255", "to_base": "hex"})
# {"result": {"state": {"result": "FF", "outputs": ["FF", "CCLV"]}}}
```

Try asking: "Convert 255 from decimal to hexadecimal and to binary and tell me both results."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Qonvert 12. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 12 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The number must use digits of the input base (for hex: 0-9 and a-f).
- Which extra rows appear (fractions, Roman numerals) depends on the value: integers get Roman numerals, fractions get continued fractions.
- Fractions use the app notation 8/5 and mixed numbers 1_3/5.

### Popups and first-run screens handled

- None.
