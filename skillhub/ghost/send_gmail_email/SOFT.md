---
generated_with: ghost skill migrate
source: v1 class docstrings, elements*.yaml, recorded.json, FLOW.md
---

# send_gmail_email: SOFT notes (LLM-adaptable narrative)

Auto-generated skill from 6 recorded steps

Target: `com.google.android.gm` on android. Each action below wraps the v1 implementation unchanged (see `helpers.py`); this file is the reference an agent uses to adapt the skill when the replay fails on a different device or app version.

## Actions

### `recorded(subject, body)`

Auto-generated skill from 6 recorded steps.

Recorded steps:

1. `launch`: Launch the Gmail app (goal: Ensure Gmail is open)
2. `tap`: Tap the To autocomplete field to ensure it's focused (goal: Focus To field)
3. `type`: Type email subject: Subject field is already focused (goal: Set subject)
4. `tap`: Tap the Compose email body field (goal: Focus body)
5. `type`: Type email body text (goal: Write body)
6. `tap`: Tap the Send button (goal: Send email)

Params:

- `subject` (str, required): e.g. Test email subject
- `body` (str, required): e.g. Hello, this is a test email sent via automation.

Success: the wrapped v1 run reports success (`helpers:v1_ok`); the replayed `RecordedWorkflow` decides.

## Login state

This recorded action requires `logged_in`. Start on the signed-in compose screen with the Send control visible, as the original recording expects. Its read-only probe uses that positive selector; a different screen, language or unreadable UI stops with `needs_state`. This skill has no automatic login provider. auto-login runner: beta.
