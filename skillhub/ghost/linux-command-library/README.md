# Control Linux Command Library on Android with an AI agent

**Control Linux Command Library on Android with an AI agent.** Look up Linux commands offline: an agent searches a command and reads its examples, synopsis and options.

Target search phrase: _AI agent looks up Linux commands on Android_

Demo shows: `search_commands (query=tar)`

> Ghost in the Droid seed skill for Linux Command Library (`com.inspiredandroid.linuxcommandbibliotheca`), an offline reference of Linux commands. Search results, section headers and the text of each section are plain nodes, so an agent can look up exact examples and options. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_library` | Restart the app and read the start screen. | none |
| `search_commands` | Search commands by name; returns the number of matches and the first result names. | `query` |
| `open_command` | Open a command page by its exact name (searches for it first if needed) and list its sections. | `name` |
| `read_section` | Read one section of the open command page: TLDR (default, example pairs), SYNOPSIS, DESCRIPTION, PARAMETERS, INSTALL, CAVEATS, HISTORY or SEE ALSO. | `section` |
| `get_state` | Read the current screen: start, search results or an open command with its visible sections. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_library |
| Primitives | search_commands, open_command, read_section |
| Read state | get_state |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.inspiredandroid.linuxcommandbibliotheca/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/linux-command-library
```

## Use

```bash
ghost skill run ghost/linux-command-library open_command --param name=tar --device <serial>
ghost skill run ghost/linux-command-library read_section --param section=TLDR --device <serial>
```

```python
run_skill(name="ghost/linux-command-library", action="read_section", params={"section": "TLDR"})
# {"result": {"lines": ["Create an archive from files", "tar -cvf [archive.tar] [file1] [file2]", ...]}}
```

Try asking: "Open the tar command in the Linux command library and tell me how to extract a gzip compressed archive."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Linux Command Library 175. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 175 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Not every command has every section; read_section lists the sections it found when one is missing.
- open_command needs the exact name; use search_commands to find it.
- Long sections are read by scrolling, which can take several seconds.

### Popups and first-run screens handled

- None.
