# Android Skill Execution Engine

Reliable, self-healing automation runtime for Android apps. Every skill workflow runs through a standard lifecycle that handles screen state, app launch, and popup dismissal automatically — so skill authors only write the happy path.

## Execution Lifecycle

```
┌─────────────────────────────────────────────┐
│  0. Wake screen (KEYCODE_WAKEUP)            │
│  1. Back-spam ×5 (reset deep navigation)    │
│  2. Home button (guaranteed home screen)    │
│  3. Launch app (monkey launcher intent)     │
│  4. Popup detect (skill-specific)           │
│                                             │
│  ┌─ Step loop ────────────────────────────┐ │
│  │  5. Execute action                     │ │
│  │  6. Popup detect (up to 3 chained)     │ │
│  │  7. Next step → goto 5                 │ │
│  └────────────────────────────────────────┘ │
│                                             │
│  N. Return result (success/fail + timing)   │
└─────────────────────────────────────────────┘
```

Every workflow gets this for free. No boilerplate needed in skill code.

## Popup Detectors

Each skill declares popup patterns in `skill.yaml`:

```yaml
popup_detectors:
  - detect: "Turn on notifications"     # text to find in XML dump
    button: "Not now"                   # button to tap to dismiss
    label: "Notifications popup"        # human-readable name
  - detect: "Continue editing"
    button: "Save draft"
    label: "Draft resume overlay"
  - detect: "Learn more"
    button: "_back"
    label: "Invisible promo overlay"
    method: "back"                      # press Back instead of tapping
```

**Detection methods:**
- **XML text match** — scans the UI dump for the `detect` string, then taps the `button` by text/content-desc
- **Back press** — for invisible overlays that can't be tapped (`method: "back"`)
- **Generic fallback** — clickable buttons matching common dismiss words (Not now, Skip, Cancel, etc.)

**Current popup libraries:**
| Skill | Detectors | Examples |
|-------|-----------|----------|
| TikTok | 10 | Draft resume, contacts, Facebook, TikTok Shop, notifications, security |
| Instagram | 4 | Notifications, save login, add account, permissions |
| Base (generic) | 6 | Not now, Skip, Cancel, Dismiss, Later, Allow |

## Per-Step Control

Workflows can customize the engine behavior:

```python
class MyWorkflow(Workflow):
    auto_launch = False        # skip wake/home/launch (already in the app)
    skip_popup_detect = False  # set True to disable popup checks between steps
```

## Skill Compatibility Tracking

Every execution is recorded in the database:

- **`skill_runs`** table — one row per execution attempt (device, skill, workflow, status, duration, error, app version)
- **`skill_compat`** table — aggregated pass/fail counts per device+skill+workflow

### Verify Mode

The Skill Hub UI has a **Verify** button per device that runs all workflows and records results. Use this when:
- Setting up a new device
- After an app update (resource IDs may have changed)
- After installing a new skill

### API

```
GET  /api/skills/compat?device=SERIAL     # compatibility matrix
GET  /api/skills/runs?device=X&skill=Y    # execution history
POST /api/skills/{name}/verify            # run verification test
DELETE /api/skills/compat/{device}/{skill} # reset status for re-test
```

## Default Parameters

Skills define sensible defaults in `skill.yaml` so users don't need to type JSON:

```yaml
default_params:
  workflows:
    upload_video:
      video_path: "/tmp/video.mp4"
      caption: "Check this out!"
    publish_draft:
      draft_index: 0
  actions:
    type_and_search:
      query: "#cats"
```

The Skill Hub run modal pre-fills these automatically.

## Architecture

```
skill.yaml
  ├── popup_detectors[]    → loaded by Skill._load_metadata()
  ├── default_params{}     → served via /api/skills/{name}
  └── exports              → actions + workflows

Workflow.run()
  ├── _wake_and_reset()    → WAKEUP + back ×5 + HOME
  ├── _launch_app()        → monkey -p {app_package}
  ├── _dismiss_popups()    → Device.dismiss_popups(popups=skill.popup_detectors)
  └── for step in steps:
      ├── action.run()     → pre/execute/post with retry
      └── _dismiss_popups()

Device.dismiss_popups(xml, popups=None)
  ├── Skill-specific popup list (if provided)
  ├── Global _KNOWN_POPUPS fallback
  ├── Generic dismiss-word matching
  └── Invisible overlay detection (Back press)
```

## Files

| File | Purpose |
|------|---------|
| `gitd/skills/base.py` | Skill, Action, Workflow, Element base classes |
| `gitd/skills/_run_skill.py` | CLI entry point + DB tracking |
| `gitd/skills/*/skill.yaml` | Per-skill popup detectors + default params |
| `gitd/models/skill_compat.py` | SkillRun + SkillCompat ORM models |
| `gitd/routers/skills.py` | API endpoints (list, run, verify, compat) |
| `frontend/src/views/SkillHubView.vue` | Skill management UI with compat + verify |
| `gitd/bots/common/adb.py` | Device.dismiss_popups() with skill popup support |
