# Control Samsung and Google Clock on Android with an AI agent

Start, cancel and inspect Samsung timers; use the existing Google Clock alarm, timer, stopwatch and world-city toolkit. Timer actions detect the installed app. No account is needed.

Try asking: **Start a one-minute Samsung timer, then cancel it and check that it stopped.**

## Toolkit

| Action | App | What it does | Params |
|---|---|---|---|
| start_timer | Samsung or Google | Start and validate the requested duration | seconds, app=auto/google/samsung, label (Google only) |
| cancel_timer | Samsung | Cancel the active timer; no-op if none active | app=auto/samsung |
| get_timer_state | Samsung | Return active=true/false, including paused timers | app=auto/samsung |
| set_alarm | Google only | Create and validate an alarm | hour, minute, label |
| list_alarms | Google only | Read alarm time, label, repeat and enabled state | none |
| start_stopwatch | Google only | Start and validate the stopwatch | none |
| add_world_city | Google only | Add and validate a world-clock city | city |

## Samsung timer behavior

Auto selection prefers installed Samsung Clock, then Google Clock; app=google forces Google when installed. A missing requested app fails explicitly. Samsung uses only Timer and never opens its Alarm tab. An existing active Samsung timer is preserved: start_timer refuses to replace it. Its duration is set through the identified number pickers, reread before Start, and validated with the active timer service plus Pause control. It does not create named timer presets. Custom Samsung labels are unsupported and fail before starting; omit label or use the default Timer.

Cancellation requires the currently visible Samsung cancellation control and verifies the timer notification service stopped. SHOW_TIMERS opens an add-timer picker while another timer is active, so cancellation does not navigate away from the countdown. get_timer_state reports whether a timer is active, including paused timers; it does not claim remaining time. No alarm definitions are deleted.

The bundled app-scoped snapshot reads visible Clock nodes without an idle wait. Normal uiautomator dump can stall during an animated countdown. Snapshot failure fails closed; no root, network or installed helper APK is required for Samsung timer actions.

## Use

```bash
ghost skill run ghost/clock start_timer --param seconds=60 --param app=samsung
ghost skill run ghost/clock cancel_timer --param app=samsung
ghost skill run ghost/clock get_timer_state --param app=samsung
```

Use a device returned by list_devices or configure GHOST_DEVICE. From MCP, call find_skill, then run_skill with the selected device. Google-only actions retain their existing Google Clock targets.

## Verification scope

The current primary fingerprint targets Samsung Clock >=12, Android >=13, with Google Clock declared as a companion. Samsung SM-A156B verification uses the Timer page on Samsung SM-A156B, Android 16, Samsung Clock 12.5.60.29, English UI. Three clean-reset start/cancel/state cycles passed; paused-timer state was also checked. See current signed runs for measured outcomes. Existing Google evidence below belongs to its recorded skill versions; no new Google physical-device run is claimed. Demos must cancel their owned timer and restore the original picker afterward.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 7.4 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0, 1.0.1 | 16/17 | 2026-10-05 |

Android 13 was additionally replayed on Samsung SM-A037F (720x1600, 300 dpi, en-GB) and an emulator (1080x2400, 420 dpi, en-US). See [the cross-device report](../../../docs/reports/samsung-failure-fixes.md) for measured outcomes and limitations; other profiles remain unverified.

Stale or noncanonical artifacts are pruned from `runs/`. Current Samsung timer self-runs cover start_timer, cancel_timer and get_timer_state. Google-only set_alarm, list_alarms, start_stopwatch and add_world_city are unverified on the current build; no Google Clock install or alarm interaction is performed on the Samsung test device.

### Recorded failures

- 2026-10-05, v1.0.0, `set_alarm`: `ValidatorFailedError`; validator ran before the new alarm card rendered, and freshly added cards report a content-desc without the time; fixed in 1.0.1 (validator scrolls and matches cards by containment).

### Popups and first-run screens handled

- None app-specific; Android permission dialogs go through the engine's OS popup layer.

### Other known failure modes

- Clock navigation and visible-state reads use the bundled read-only accessibility snapshot, including when expired timers keep background accessibility events active. Unavailable snapshots fail closed; no root or extra APK is needed for this fallback.
- 12 h vs 24 h display depends on the device setting; helpers accept both.
- A city already on the list is not duplicated; the action still succeeds.

## Historical Google compatibility through 1.0.2

The manifest targets Android >=13 and Google Clock >=7.4, with en-US and en-GB flows. The authoring screen remains 1080x2400 at 420 dpi; alarm cards and scrolling now use measured bounds for narrower screens too. Alarm validation rereads time, label and the enabled switch. `list_alarms` rewinds and rereads rows, including count. Root-readable Clock preferences remain authoritative for timer state, label/original duration and `sw_state=1`. When preferences are unreadable, the app-scoped snapshot requires a matching timer card with a decreasing countdown near the requested duration, or an increasing stopwatch with Pause exposed. Off-screen pager nodes are excluded. World-city validation rereads the city list. See [snapshot source and offline build](snapshot/README.md) and current signed runs for exercised devices.

- Intent creation still depends on Google Clock selectors during verification; slow rendering or a changed UI can fail. The `nat2` before-arm failure set no alarm within the agent turn budget; it is not evidence of an independent skill validator check.
- Alarm collection has a six-scan limit; a larger list may be incomplete.

Adding an already-visible city leaves it selected. After a new selection, the helper restores the city tab in case an expiring timer interrupted navigation, then independently checks the saved city list.

Version1.0.4 only taps Samsung timer_cancel_button when a timer_pause_button or timer_resume_button establishes the Timer screen. Generic alarm Cancel/Dismiss/Stop controls are never tapped. Samsung remains the evidence target; the Google-primary/multi-app fingerprint concern requires a separate Google-device replay and is not claimed fixed here. Picker replay coverage uses a one-minute timer; large durations remain unverified and can require many taps.

### Samsung picker startup and readback

Cold phone-B launch takes with version 1.0.4 failed the one-minute duration check before any timer started. Version 1.0.5 waits for two equal native picker snapshots before input, then observes each exact wheel step with a bounded wait. Missing numeric input text requires the native Timer picker's hour/minute/second description; conflicting or unavailable values fail closed. It never repeats a tap blindly or presses Start without the requested duration. The Google-only actions remain unverified on phone B.
