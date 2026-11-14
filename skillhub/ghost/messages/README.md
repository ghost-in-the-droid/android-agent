# messages

Demo shows: `draft_message (number=5550100, text=See you at 6)`

> Ghost in the Droid seed skill for Google Messages (`com.google.android.apps.messaging`). Works without an account. Never sends a message.

| Action | What it does | Params |
|---|---|---|
| `draft_message` | Save an unsent SMS draft to a number | `number`, `text` |
| `list_conversations` | Conversation rows with snippet, time, draft and unread flags | none |
| `read_conversation` | Messages in the thread with a number | `number` |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/messages
```

## Use

```bash
ghost skill run ghost/messages draft_message --param number=5550100 --param "text=See you at 6" --device emulator-5554
ghost skill run ghost/messages read_conversation --param number=5550100 --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/messages", action="list_conversations")
# {"conversations": [{"name": "Grace Hopper", "snippet": "You: See you at 6", "time": "Draft", "is_draft": true, "unread": false}], "count": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Messages 20230529, en-US. Signed self-runs live in `runs/`.

## Notes

Sending is left to a human: open the draft and tap Send. The skill opens threads by intent and never taps notification smart replies, which send instantly. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| messages.android_20230529_03_RC01_alldpi.x86_64.phone | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 9/9 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- First-run Google sign-in screen
- Notification permission prompt

### Other known failure modes

- Signed-in Messages (RCS) shows chat features and different first-run screens.
- A number that matches a contact shows the contact name as the title; the helpers do not depend on the title text.
