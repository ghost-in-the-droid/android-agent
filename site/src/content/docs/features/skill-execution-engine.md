---
title: "⚙️ Execution Engine"
description: Self-healing automation runtime with standard lifecycle, popup detection, compatibility tracking, and per-device verification.
---

Reliable, self-healing automation runtime for Android apps. Every skill workflow runs through a standard lifecycle that handles screen state, app launch, and popup dismissal automatically — so skill authors only write the happy path.

## Execution Lifecycle

Every workflow follows this sequence:

| Phase | What happens |
|-------|-------------|
| **0. Wake** | `KEYCODE_WAKEUP` — ensures screen is on |
| **1. Back-spam** | Press Back ×5 — dismiss any deep navigation |
| **2. Home** | Press Home — guaranteed clean starting point |
| **3. Launch** | Monkey launcher intent for the skill's `app_package` |
| **4. Popup detect** | Run all skill-defined popup detectors |
| **5–N. Steps** | Execute each action, then popup detect after each |

```python
# Skill authors just define the steps — the engine handles the rest
class UploadVideo(Workflow):
    name = 'upload_video'
    
    def steps(self):
        return [
            OpenApp(self.device, self.elements),
            TapUploadButton(self.device, self.elements),
            SelectVideo(self.device, self.elements, path=self.video_path),
            SetCaption(self.device, self.elements, text=self.caption),
            TapPost(self.device, self.elements),
        ]
```

### Control Flags

Workflows can customize the engine:

```python
class QuickAction(Workflow):
    auto_launch = False        # skip wake/home/launch — already in the app
    skip_popup_detect = True   # no popup checks between steps
```

## Popup Detectors

Each skill declares popup patterns in `skill.yaml`:

```yaml
popup_detectors:
  - detect: "Turn on notifications"
    button: "Not now"
    label: "Notifications popup"
  - detect: "Continue editing"
    button: "Save draft"
    label: "Draft resume overlay"
  - detect: "Learn more"
    button: "_back"
    label: "Invisible promo overlay"
    method: "back"
```

### Detection Methods

| Method | How it works |
|--------|-------------|
| **XML text match** | Scans the UI dump for the `detect` string, taps `button` by text |
| **Back press** | For invisible overlays (`method: "back"`) |
| **Generic fallback** | Matches common dismiss words: Not now, Skip, Cancel, Dismiss, Later |
| **Pixel detection** | Red-band scan for TikTok's draft resume overlay (invisible to uiautomator) |

### Per-Skill Libraries

| Skill | Detectors | Covers |
|-------|-----------|--------|
| **TikTok** | 10 | Draft resume, contacts, Facebook, TikTok Shop, notifications, security, promo overlays |
| **Instagram** | 4 | Notifications, save login, add account, permission requests |
| **Base** | 6 | Generic: Not now, Skip, Cancel, Dismiss, Later, Allow |

Popups are dismissed up to 3 in a chain (handles stacked dialogs).

## Compatibility Tracking

Every execution is recorded automatically in the database.

### Tables

- **`skill_runs`** — one row per execution (device, skill, workflow, status, duration, error, app version)
- **`skill_compat`** — aggregated pass/fail per device + skill + workflow

### Verify Mode

The Skill Hub has a **Verify** button per device. It runs all workflows on the device and records which ones pass or fail. Use this:

- When setting up a new phone
- After an app update changes resource IDs
- After installing a new skill

Results show as colored badges: **OK** (green), **FAIL** (red), **UNTESTED** (gray).

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/skills/compat?device=SERIAL` | Compatibility matrix |
| `GET` | `/api/skills/runs?device=X&skill=Y` | Execution history |
| `POST` | `/api/skills/{name}/verify` | Run verification test |
| `DELETE` | `/api/skills/compat/{device}/{skill}` | Reset for re-test |

## Default Parameters

Skills define defaults in `skill.yaml` so the UI pre-fills the run modal:

```yaml
default_params:
  workflows:
    upload_video:
      video_path: "/tmp/video.mp4"
      caption: "Check this out!"
    publish_draft:
      draft_index: 0
  actions:
    launch_app:
      package: "com.zhiliaoapp.musically"
```

## Key Files

| File | Purpose |
|------|---------|
| `skills/base.py` | Skill, Action, Workflow base classes + execution engine |
| `skills/_run_skill.py` | CLI entry point, DB tracking |
| `skills/*/skill.yaml` | Per-skill popup detectors, default params, metadata |
| `models/skill_compat.py` | SkillRun + SkillCompat ORM |
| `routers/skills.py` | REST API for skills, compat, verify |
| `bots/common/adb.py` | Device.dismiss_popups() with skill-specific popup support |
