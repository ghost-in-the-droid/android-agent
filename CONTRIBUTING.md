# Contributing

Thanks for your interest in contributing! This guide covers how to get involved, whether you're fixing a bug, adding a skill for a new app, or improving docs.

---

## Ways to Contribute

| Type | Difficulty | Impact |
|------|-----------|--------|
| Report a bug | Easy | High |
| Improve documentation | Easy | High |
| Add UI elements for a new app | Easy-Medium | High |
| Write an Action for an existing app | Medium | High |
| Write a Workflow (multi-step) | Medium | High |
| Build a complete app Skill | Medium-Hard | Very High |
| Core framework contribution | Hard | Very High |

**The highest-impact contribution is adding skills for new apps.** Every new app skill makes the framework more useful for everyone.

---

## Development Setup

### Prerequisites

- Python 3.10+
- Android phone with USB debugging enabled (or Android emulator)
- ADB installed and on PATH (`adb devices` shows your device)

### Install

```bash
git clone https://github.com/ghost-in-the-droid/ghost-in-the-droid.git
cd ghost-in-the-droid
pip install -e ".[all]"
```

### Verify

```bash
# Check ADB sees your device
adb devices

# Run tests (requires connected phone)
DEVICE=<your_serial> python3 -m pytest tests/ -v --tb=short

# Start the dashboard
python3 run.py
# Open http://localhost:5055
```

---

## Adding a Skill for a New App

This is the most common and valuable contribution. A skill is a folder with UI element definitions and Python automation code.

### 1. Scaffold

```bash
# Creates the skill folder structure
mkdir -p gitd/skills/whatsapp/actions
mkdir -p gitd/skills/whatsapp/workflows
```

### 2. Define UI Elements (`elements.yaml`)

Use the **Skill Creator** tab in the dashboard (Phone stream + element overlay) to identify elements:

```yaml
# gitd/skills/whatsapp/elements.yaml
package: com.whatsapp
app_version: "2.24.x"

elements:
  search_icon:
    resource_id: "com.whatsapp:id/menuitem_search"
    description: "Search icon in toolbar"
    
  chat_input:
    resource_id: "com.whatsapp:id/entry"
    description: "Message text input field"
    
  send_button:
    resource_id: "com.whatsapp:id/send"
    description: "Send message button"
```

### 3. Write Actions

Each action is a Python class that performs one atomic operation:

```python
# gitd/skills/whatsapp/actions/send_message.py
from gitd.skills.base import Action

class SendMessage(Action):
    """Type and send a message in an open chat."""
    
    name = "send_message"
    description = "Type a message and tap send"
    
    def precondition(self, dev, xml):
        # Verify we're in a chat (input field visible)
        return dev.find_bounds(xml, resource_id="com.whatsapp:id/entry") is not None
    
    def execute(self, dev, text="Hello"):
        xml = dev.dump_xml()
        dev.tap_text(xml, resource_id="com.whatsapp:id/entry")
        dev.adb("shell", "input", "text", text)
        
        xml = dev.dump_xml()
        dev.tap_text(xml, resource_id="com.whatsapp:id/send")
        return True
```

### 4. Write Workflows (Optional)

Workflows chain multiple actions into a multi-step sequence:

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
            ("search_contact", {"query": self.params["contact"]}),
            ("send_message", {"text": self.params["message"]}),
        ]
```

### 5. Register the Skill

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
# Verify skill loads
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
action = s.get_action('send_message')
action.run(dev, text='Hello from the bot')
"
```

### 7. Submit PR

```bash
git checkout -b skill/whatsapp
git add gitd/skills/whatsapp/
git commit -m "Add WhatsApp skill: send_message action, send_dm workflow"
```

Open a PR with:
- What app and version you tested on
- What device (model, Android version)
- Screenshot of the skill working (optional but appreciated)

---

## Code Contributions

### Backend Architecture

The server is **FastAPI + SQLAlchemy 2.0 + Pydantic v2**:

```
gitd/
  app.py              # FastAPI app factory + router registration
  config.py           # Pydantic settings from .env
  models/             # SQLAlchemy 2.0 ORM (11 tables)
  schemas/            # Pydantic v2 request/response models
  routers/            # FastAPI route handlers (14 routers)
  services/           # Business logic + shared helpers
  alembic/            # Database migrations
```

- Use `db: Session = Depends(get_db)` for database access in routes
- Use `sqlalchemy.text()` for complex SQL, ORM for simple CRUD
- Run `alembic revision --autogenerate -m "desc"` after model changes
- Auto-generated API docs at `http://localhost:5055/docs`

### Code Style

- Python 3.10+ with type hints
- Lint with `ruff check gitd/`
- Format with `ruff format gitd/`
- Prefer simple, readable code over clever abstractions
- Keep functions focused — one function, one job

### PR Process

1. Fork the repo
2. Create a branch (`feature/thing` or `fix/thing`)
3. Make your changes
4. Run tests: `python3 -m pytest tests/ -v --tb=short`
5. Open a PR with a clear description of what and why

### What Makes a Good PR

- **Small and focused** — one feature or fix per PR
- **Tested** — include test commands or evidence it works
- **Documented** — update relevant docs if behavior changes
- **No unrelated changes** — don't refactor surrounding code

### What to Avoid

- Don't add dependencies without discussion
- Don't change the database schema without a migration
- Don't modify API response formats (breaks dashboard)
- Don't commit API keys, credentials, or personal data

---

## Reporting Bugs

Open a GitHub issue with:

1. **What happened** (actual behavior)
2. **What you expected** (expected behavior)
3. **Steps to reproduce**
4. **Device info** (phone model, Android version, app version)
5. **Logs** (relevant error output)
6. **Screenshot** (if UI-related)

---

## Questions?

- Open a GitHub Discussion for questions
- Join our Discord for real-time help
- Tag `@maintainers` for urgent issues
