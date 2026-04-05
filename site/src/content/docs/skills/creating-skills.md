---
title: "🔨 Creating Skills"
description: Step-by-step guide to building a new skill — scaffold, elements, actions, workflows, registration, and testing.
---

Adding a skill for a new app is the most valuable contribution you can make. This guide walks through the full process using WhatsApp as an example.

## Step 1: Scaffold the Directory

```bash
mkdir -p gitd/skills/whatsapp/actions
mkdir -p gitd/skills/whatsapp/workflows
touch gitd/skills/whatsapp/__init__.py
touch gitd/skills/whatsapp/actions/__init__.py
touch gitd/skills/whatsapp/workflows/__init__.py
```

## Step 2: Create skill.yaml

```yaml
# gitd/skills/whatsapp/skill.yaml
name: whatsapp
display_name: WhatsApp
version: "1.0.0"
app_package: com.whatsapp
description: WhatsApp messaging automation
author: your_name
```

## Step 3: Define Elements (elements.yaml)

Use the **Skill Creator** tab in the dashboard to visually identify interactive elements on the target app. The element overlay shows numbered labels on each interactive element.

Alternatively, dump the XML and inspect:

```python
from gitd.bots.common.adb import Device
dev = Device()
dev.adb("shell", "am", "start", "-n", "com.whatsapp/.Main")
import time; time.sleep(3)
xml = dev.dump_xml()
for n in dev.nodes(xml):
    rid = dev.node_rid(n)
    text = dev.node_text(n)
    desc = dev.node_content_desc(n)
    if rid or text or desc:
        print(f"RID={rid}  text={text}  desc={desc}")
```

Write the elements file with a fallback chain per element:

```yaml
# gitd/skills/whatsapp/elements.yaml
package: com.whatsapp
app_version: "2.24.x"

elements:
  search_icon:
    resource_id: "com.whatsapp:id/menuitem_search"
    content_desc: "Search"
    description: "Search icon in toolbar"

  search_input:
    resource_id: "com.whatsapp:id/search_src_text"
    class_name: "android.widget.EditText"
    description: "Search text input"

  chat_input:
    resource_id: "com.whatsapp:id/entry"
    description: "Message text input field"

  send_button:
    resource_id: "com.whatsapp:id/send"
    content_desc: "Send"
    description: "Send message button"

  contact_row:
    resource_id: "com.whatsapp:id/contact_row_container"
    description: "Contact list row"
```

The fallback priority is: `content_desc` -> `text` -> `resource_id` -> `class_name` -> `(x, y)` absolute coordinates.

## Step 4: Write Actions

Each action is a Python class extending `Action`. At minimum, implement `execute()`:

```python
# gitd/skills/whatsapp/actions/core.py
from gitd.skills.base import Action, ActionResult

class OpenApp(Action):
    """Launch WhatsApp."""
    name = "open_app"
    description = "Force-stop and relaunch WhatsApp"

    def execute(self, dev, **kwargs):
        dev.adb("shell", "am", "force-stop", "com.whatsapp")
        dev.adb("shell", "am", "start", "-n", "com.whatsapp/.Main")
        import time; time.sleep(3)
        return ActionResult(success=True)

    def postcondition(self, dev, xml):
        # Verify WhatsApp is in foreground
        return "com.whatsapp" in dev.adb("shell", "dumpsys", "activity", "top")


class SearchContact(Action):
    """Search for a contact by name."""
    name = "search_contact"
    description = "Tap search and type a contact name"

    def execute(self, dev, query="", **kwargs):
        xml = dev.dump_xml()
        bounds = dev.find_bounds(xml, content_desc="Search")
        if bounds:
            dev.tap(*dev.bounds_center(bounds))
            import time; time.sleep(1)
            dev.type_text(query)
            dev.press_enter()
            time.sleep(2)
            return ActionResult(success=True)
        return ActionResult(success=False, error="Search icon not found")


class SendMessage(Action):
    """Type and send a message in an open chat."""
    name = "send_message"
    description = "Type a message and tap send"

    def precondition(self, dev, xml):
        return dev.find_bounds(xml, resource_id="com.whatsapp:id/entry") is not None

    def execute(self, dev, text="Hello", **kwargs):
        xml = dev.dump_xml()
        bounds = dev.find_bounds(xml, resource_id="com.whatsapp:id/entry")
        dev.tap(*dev.bounds_center(bounds))
        dev.type_text(text)
        import time; time.sleep(0.5)

        xml = dev.dump_xml()
        bounds = dev.find_bounds(xml, resource_id="com.whatsapp:id/send")
        if bounds:
            dev.tap(*dev.bounds_center(bounds))
            return ActionResult(success=True)
        return ActionResult(success=False, error="Send button not found")
```

## Step 5: Write Workflows (Optional)

Workflows chain actions into multi-step sequences:

```python
# gitd/skills/whatsapp/workflows/send_dm.py
from gitd.skills.base import Workflow

class SendDM(Workflow):
    """Open WhatsApp, find a contact, send a message."""
    name = "send_dm"
    description = "Send a DM to a contact by name"

    def steps(self):
        return [
            ("open_app", {}),
            ("search_contact", {"query": self.params.get("contact", "")}),
            ("send_message", {"text": self.params.get("message", "Hello!")}),
        ]
```

## Step 6: Register the Skill

```python
# gitd/skills/whatsapp/__init__.py
from gitd.skills.base import Skill

def load():
    skill = Skill.from_yaml("gitd/skills/whatsapp")

    from .actions.core import OpenApp, SearchContact, SendMessage
    skill.register_action(OpenApp)
    skill.register_action(SearchContact)
    skill.register_action(SendMessage)

    from .workflows.send_dm import SendDM
    skill.register_workflow(SendDM)

    return skill
```

## Step 7: Test

```python
# Verify the skill loads
python3 -c "
from gitd.skills.whatsapp import load
s = load()
print(f'{s.name}: {len(s.elements)} elements')
print(f'Actions: {s.list_actions()}')
print(f'Workflows: {s.list_workflows()}')
"

# Run an action on a connected device
python3 -c "
from gitd.skills.whatsapp import load
from gitd.bots.common.adb import Device
s = load()
dev = Device()
action = s.get_action('open_app', dev)
result = action.run()
print(f'Success: {result.success}')
"
```

## Using the Skill Creator Tool

The **Skill Creator** tab provides a faster way to identify elements and test actions:

1. Start the WebRTC stream for your device
2. Open the Skill Creator tab
3. Select an LLM backend (OpenRouter, Claude, Ollama, or Claude Code)
4. Describe what you want: "Open WhatsApp and find the search icon"
5. The LLM sees the current screen elements and proposes action steps
6. Click Execute to test each step on the device
7. Use the element overlay to find resource IDs and content descriptions

## Next Steps

- [Elements](/skills/elements/) -- deep dive into locator chains and elements.yaml format
- [Publishing](/skills/publishing/) -- share your skill with the community
- [Skill System Reference](/features/skill-system/) -- full class API documentation
