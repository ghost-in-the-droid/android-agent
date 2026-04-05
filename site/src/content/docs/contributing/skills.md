---
title: "🧩 Contribute Skills"
description: How to contribute a skill for a new Android app — the highest-impact contribution.
---

**Adding skills for new apps is the most valuable contribution.** Every new app skill makes the framework more useful for everyone. This page covers the process specifically for contributors.

## Contribution Types

| Type | Difficulty | Impact |
|------|-----------|--------|
| Add UI elements for a new app | Easy-Medium | High |
| Write an Action for an existing app | Medium | High |
| Write a Workflow (multi-step) | Medium | High |
| Build a complete app Skill | Medium-Hard | Very High |

## Step-by-Step

### 1. Scaffold the Directory

```bash
mkdir -p gitd/skills/whatsapp/actions
mkdir -p gitd/skills/whatsapp/workflows
touch gitd/skills/whatsapp/__init__.py
touch gitd/skills/whatsapp/actions/__init__.py
touch gitd/skills/whatsapp/workflows/__init__.py
```

### 2. Define UI Elements

Use the **Skill Creator** tab (live device stream with element overlay) to identify elements on the target app:

```yaml
# gitd/skills/whatsapp/elements.yaml
package: com.whatsapp
app_version: "2.24.x"

elements:
  search_icon:
    resource_id: "com.whatsapp:id/menuitem_search"
    content_desc: "Search"
    description: "Search icon in toolbar"

  chat_input:
    resource_id: "com.whatsapp:id/entry"
    description: "Message text input field"

  send_button:
    resource_id: "com.whatsapp:id/send"
    content_desc: "Send"
    description: "Send message button"
```

Always provide at least 2 locator fields per element (e.g., `resource_id` + `content_desc`).

### 3. Write Actions

```python
# gitd/skills/whatsapp/actions/send_message.py
from gitd.skills.base import Action, ActionResult

class SendMessage(Action):
    name = "send_message"
    description = "Type a message and tap send"

    def precondition(self, dev, xml):
        return dev.find_bounds(xml, resource_id="com.whatsapp:id/entry") is not None

    def execute(self, dev, text="Hello", **kwargs):
        xml = dev.dump_xml()
        bounds = dev.find_bounds(xml, resource_id="com.whatsapp:id/entry")
        dev.tap(*dev.bounds_center(bounds))
        dev.type_text(text)

        xml = dev.dump_xml()
        bounds = dev.find_bounds(xml, resource_id="com.whatsapp:id/send")
        if bounds:
            dev.tap(*dev.bounds_center(bounds))
            return ActionResult(success=True)
        return ActionResult(success=False, error="Send button not found")
```

### 4. Write Workflows (Optional)

```python
# gitd/skills/whatsapp/workflows/send_dm.py
from gitd.skills.base import Workflow

class SendDM(Workflow):
    name = "send_dm"
    description = "Send a DM to a contact"

    def steps(self):
        return [
            ("open_app", {}),
            ("search_contact", {"query": self.params["contact"]}),
            ("send_message", {"text": self.params["message"]}),
        ]
```

### 5. Register

```python
# gitd/skills/whatsapp/__init__.py
from gitd.skills.base import Skill

def load():
    skill = Skill.from_yaml("gitd/skills/whatsapp")
    from .actions.send_message import SendMessage
    skill.register_action(SendMessage)
    from .workflows.send_dm import SendDM
    skill.register_workflow(SendDM)
    return skill
```

### 6. Test

```bash
# Verify it loads
python3 -c "
from gitd.skills.whatsapp import load
s = load()
print(f'{s.name}: {len(s.elements)} elements, {s.list_actions()}, {s.list_workflows()}')
"

# Run on device
python3 -c "
from gitd.skills.whatsapp import load
from gitd.bots.common.adb import Device
s = load()
dev = Device()
action = s.get_action('send_message', dev)
result = action.run(text='Hello from the bot')
print(f'Success: {result.success}')
"
```

### 7. Submit PR

```bash
git checkout -b skill/whatsapp
git add gitd/skills/whatsapp/
git commit -m "Add WhatsApp skill: send_message action, send_dm workflow"
```

Include in the PR:

- App name and version tested on
- Device model and Android version
- What actions and workflows are included
- Screenshot of the skill working (appreciated but optional)

## Quality Checklist

Before submitting:

- [ ] `skill.yaml` has `name`, `version`, `app_package`, `description`
- [ ] `elements.yaml` uses multiple locator fields per element
- [ ] All actions have `name` and `description`
- [ ] At least one action has a `postcondition()`
- [ ] Skill loads without errors
- [ ] Tested on a real device
- [ ] No hardcoded serials or credentials

## Even Partial Skills Help

Even a skeleton with just `skill.yaml` and `elements.yaml` (no actions) is a valid contribution. It saves the next person from starting from scratch and provides the UI element mappings for the app.

## Related

- [Creating Skills Guide](/skills/creating-skills/) -- detailed walkthrough
- [Elements Reference](/skills/elements/) -- how locator chains work
- [Code Contributions](/contributing/code/) -- general PR guidelines
