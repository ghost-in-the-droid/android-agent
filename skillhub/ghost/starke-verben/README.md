# Control Starke Verben on Android with an AI agent

**Control Starke Verben on Android with an AI agent.** Learning German? Your agent looks up any strong verb with all its forms and quizzes you on it.

Target search phrase: _AI agent teaches German strong verbs on Android_

Demo shows: `get_verb (verb=essen)`

> Ghost in the Droid seed skill for Starke Verben (`org.sw24softwares.starkeverben`), an offline trainer for German strong verbs. Lesson, list and test screens are text nodes, so an agent can look up a verb, read all its forms and take the fill-in test. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_verbs` | Restart the app and read the first lesson verb. | none |
| `next_lesson` | Show another lesson verb and return it with all its forms. | none |
| `get_lesson` | Read the verb on the Lesson tab: infinitive, preterite, auxiliary, participle, 3rd person and translation. | none |
| `get_verb` | Look up a German strong verb by infinitive and return all its forms. | `verb` |
| `start_test` | Open a test question: one field is filled in, the rest are empty. | none |
| `answer_test` | Fill the empty fields of the open test question, tick sein or haben, press Verify and return the correct forms with a right or wrong flag per typed field. | `infinitive`, `preterite`, `participle`, `third_person`, `translation`, `auxiliary` |
| `finish_test` | Close the test result screen and return to the Test tab. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_verbs |
| Primitives | next_lesson, get_verb, start_test, answer_test, finish_test |
| Read state | get_lesson |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.sw24softwares.starkeverben/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/starke-verben
```

## Use

```bash
ghost skill run ghost/starke-verben get_verb --param verb=essen --device <serial>
```

```python
run_skill(name="ghost/starke-verben", action="get_verb", params={"verb": "essen"})
```

Try asking: "Look up the German strong verb essen with all its forms, then show me another verb lesson."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Starke Verben 16. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 16 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Only the infinitive of a strong verb is found.
- Typed answers cannot contain umlauts.

### Popups and first-run screens handled

- None.
