---
title: "📦 Publishing Skills"
description: How to share your skill — PR process, quality checklist, and skill tiers.
---

Skills are shared by contributing them to the repository. This page covers the PR process, quality standards, and how skills are classified.

## Submitting a Skill

### 1. Create a Branch

```bash
git checkout -b skill/whatsapp
```

### 2. Add Your Files

Your skill directory should include:

```
gitd/skills/whatsapp/
  skill.yaml              # Required: name, version, app_package
  elements.yaml           # Required: UI locators with fallback chains
  __init__.py             # Required: load() function
  actions/
    __init__.py
    core.py               # One or more action files
  workflows/              # Optional
    __init__.py
    send_dm.py
```

### 3. Commit and Push

```bash
git add gitd/skills/whatsapp/
git commit -m "Add WhatsApp skill: send_message action, send_dm workflow"
git push -u origin skill/whatsapp
```

### 4. Open a PR

Include in the PR description:

- **App name and version** you tested on
- **Device model and Android version**
- **What actions/workflows** are included
- **Screenshot or screen recording** of the skill working (optional but appreciated)

## Quality Checklist

Before submitting, verify:

- [ ] `skill.yaml` has `name`, `version`, `app_package`, and `description`
- [ ] `elements.yaml` has at least 2 locator fields per element (not just absolute coords)
- [ ] All actions have `name` and `description` attributes
- [ ] At least one action has a `postcondition()` that verifies success
- [ ] The skill loads without errors: `python3 -c "from gitd.skills.<name> import load; load()"`
- [ ] Actions were tested on a real device (not just emulator)
- [ ] No hardcoded device serials or credentials
- [ ] No dependencies beyond the base project requirements

## Skill Tiers

| Tier | Criteria | Example |
|------|----------|---------|
| **Skeleton** | `skill.yaml` only, no actions | Instagram |
| **Basic** | 1-3 actions, no workflows, few elements | New app scaffold |
| **Standard** | 5+ actions, 1+ workflows, 10+ elements | WhatsApp skill |
| **Complete** | Full app coverage, postconditions, retry logic, tested on multiple devices | TikTok skill |

All tiers are welcome. Even a skeleton with just `skill.yaml` and `elements.yaml` is valuable -- it saves the next person from starting from scratch.

## Export/Import

Skills can also be shared as ZIP files without going through Git:

```bash
# Export
curl http://localhost:5055/api/skills/export/whatsapp -o whatsapp_skill.zip

# Import
curl -X POST http://localhost:5055/api/skills/import -F "file=@whatsapp_skill.zip"
```

## Converting from Macros

If you built your automation as a macro first, you can convert it to a skill:

```bash
curl -X POST http://localhost:5055/api/skills/create-from-recording \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_app",
    "app_package": "com.example.app",
    "steps": [...]
  }'
```

This generates a basic skill directory with a recorded workflow. You should then add proper element definitions and split the recording into individual actions.

## Related

- [Creating Skills](/skills/creating-skills/) -- full step-by-step guide
- [Contributing Code](/contributing/code/) -- general PR process and code style
