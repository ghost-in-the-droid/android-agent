# Control Flip a coin on Android with an AI agent

**Control Flip a coin on Android with an AI agent.** Your agent flips a coin for you, once or many times, and tells you heads or tails.

Target search phrase: _AI agent flips a coin on Android to decide heads or tails_

Demo shows: `flip_many (count=5)`

> Ghost in the Droid seed skill for Flip a coin (`org.ecos.logic.flip_a_coin`), an offline coin toss. The coin exposes its face (head or tail) as an accessibility description once the animation settles, so an agent can flip and read the result. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_coin` | Restart the app and read the coin face. | none |
| `flip` | Flip the coin once and return head or tail. | none |
| `flip_many` | Flip the coin several times and return every result with the head and tail counts. | `count` |
| `get_coin` | Read the face the coin currently shows. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_coin |
| Primitives | flip, flip_many |
| Read state | get_coin |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.ecos.logic.flip_a_coin/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/flip-a-coin
```

## Use

```bash
ghost skill run ghost/flip-a-coin flip_many --param count=5 --device <serial>
```

```python
run_skill(name="ghost/flip-a-coin", action="flip")
# {"result": {"face": "tail"}}
```

Try asking: "Flip a coin five times and tell me how many heads and tails I got."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Flip a coin 3. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 3 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Count must be 1 to 20.
- If the coin does not settle within a few seconds the action raises an error.

### Popups and first-run screens handled

- None.
