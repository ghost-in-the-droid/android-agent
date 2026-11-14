# Control Oblique Strategies on Android with an AI agent

**Control Oblique Strategies on Android with an AI agent.** Stuck on a creative problem? An agent draws Oblique Strategies cards on your phone and reads them back.

Target search phrase: _AI agent draws Oblique Strategies cards on Android_

Demo shows: `draw_cards (count=4)`

> Ghost in the Droid seed skill for Oblique Strategies (`garden.lina.oblique_strategies`), the Oblique Strategies card deck (Brian Eno and Peter Schmidt). Each card is a View whose text sits in the content description, so an agent can draw cards and read them. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_deck` | Restart the app and read the card on top (the help card at first). | none |
| `draw_card` | Swipe the top card away and return the new card text. | none |
| `draw_cards` | Draw several cards (1 to 10) and return each card with its kind (help, title, strategy). | `count` |
| `get_card` | Read the card currently on top. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_deck |
| Primitives | draw_card, draw_cards |
| Read state | get_card |

## Install

The app: F-Droid, or `https://f-droid.org/packages/garden.lina.oblique_strategies/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/oblique-strategies
```

## Use

```bash
ghost skill run ghost/oblique-strategies draw_cards --param count=4 --device <serial>
```

```python
run_skill(name="ghost/oblique-strategies", action="draw_card")
# {"result": {"card": "Trust in the you of now", "kind": "strategy"}}
```

Try asking: "Draw three Oblique Strategies cards and tell me which one fits a stuck song best."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Oblique Strategies 2. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 2 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The first swipes show the help and title cards (kind help or title), not strategies.
- Cards are random; a card can be a long sentence.

### Popups and first-run screens handled

- None.
