# Control Morse on Android with an AI agent — translate text to Morse code

**Control Morse on Android with an AI agent.** Translate to and from Morse code: an agent types the text and reads the Morse (or the reverse).

Target search phrase: _AI agent translates text to Morse code on Android_

Demo shows: `translate (text=Hello World, direction=text_to_morse)`

> Ghost in the Droid seed skill for Morse (`rocks.poopjournal.morse`), an offline Morse code translator. The input and output are plain text, so an agent can encode and decode Morse exactly. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_translator` | Restart the app (denying its camera permission request) and read the translator. | none |
| `translate` | Translate text to Morse (default) or Morse to text and return the output. | `text`, `direction` |
| `get_translation` | Read the current direction, input and output. | none |
| `clear_input` | Clear the input field. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_translator |
| Primitives | translate, clear_input |
| Read state | get_translation |

## Install

The app: F-Droid, or `https://f-droid.org/packages/rocks.poopjournal.morse/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/morse-translator
```

## Use

```bash
ghost skill run ghost/morse-translator translate --param text="Hello World" --device <serial>
```

```python
run_skill(name="ghost/morse-translator", action="translate", params={"text": "SOS"})
# {"result": {"state": {"output": "... --- ..."}}}
```

Try asking: "Translate Hello World to Morse code and then decode ... --- ... back to text."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Morse 13. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 13 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Text must be plain ASCII; Morse input may only contain . - / and spaces.
- Switching the direction clears the field, so translate sets the direction first.
- The app asks for the camera permission at the first start (for the flash); open_translator denies it.

### Popups and first-run screens handled

- Camera permission dialog: denied automatically.
