# clock - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another clock app or version.

**Package**: `com.google.android.deskclock` (Google Clock)
**Historical device check**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Clock 7.4, en-US, no Google account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

Bottom tabs, all keyed by resource id `com.google.android.deskclock:id/tab_menu_<name>`: `alarm`, `clock`, `timer`, `stopwatch`, `bedtime`. One floating action button (`id/fab`) changes its content-desc per tab: `Add alarm`, `Add city`, `Add timer`, `Start` or `Pause`.

The tab pager keeps neighbouring tabs in the accessibility tree with off-screen (negative) bounds. Readers must ignore nodes whose bounds are off screen, or they will see alarms while on the Clock tab. `helpers.visible_nodes` does this.

Times render with a hair space before AM/PM (`7:30 AM`). Helpers normalise to 24 h `HH:MM`.

## Actions

### `set_alarm(hour, minute, label)`

1. Fire `android.intent.action.SET_ALARM` with `HOUR`, `MINUTES`, `MESSAGE` and `SKIP_UI=true`. This is the public AlarmClock API; this skill then opens and verifies Google Clock specifically. `label` defaults to Alarm.
2. Open the Alarm tab.
3. Success: an on-screen alarm card whose time equals `hour:minute` and whose label (`id/label`) equals `label` and whose enabled switch is checked.

### `list_alarms()`

Open the Alarm tab and read each card: the card container's content-desc is `"<time> <label>"`, inside it `id/digital_clock` (time), `id/label` (absent for the default label `Alarm`), `id/days_of_week` or `id/upcoming_instance_label`, and the `id/onoff` switch (checked state comes from the Portal tree). Read at most 6 screens, stopping if a nonempty collection stops growing. Returns `alarms: [{time, label, repeat, enabled}]`. The validator rewinds and independently rereads alarm rows, requiring exact equality and matching count.

### `start_timer(seconds, label)`

1. Fire `android.intent.action.SET_TIMER` with `LENGTH` (seconds), `MESSAGE`, `SKIP_UI=true`; the timer starts immediately in the tested app. `label` defaults to Timer.
2. Read Google Clock shared preferences through adb shell, without opening an animating tab or requesting an idle UI dump.
3. Success: one timer ID has `timer_state_<id>=1`, the requested `timer_label_<id>`, and `timer_original_timet_<id>` equal to the requested seconds × 1000.

### `start_stopwatch()`

First read `sw_state` from Google Clock shared preferences. If already 1 (running), do nothing. Otherwise open the Stopwatch tab and tap Start. The validator rereads `sw_state` and requires 1; it performs no idle UI dump after Start.

### `add_world_city(city)`

On the Clock tab tap `Add city`, type into `id/open_search_view_edit_text`, tap the first `id/city_name` result. Success: back on the Clock tab, an on-screen `id/city_name` contains the query segment before the first comma (the list shows the short name, for example `Tokyo` for `Tokyo, Japan`).

Timer and stopwatch validators read `/data/user_de/0/com.google.android.deskclock/shared_prefs/com.google.android.deskclock_preferences.xml`. This requires a root-capable adb shell on the lab image. Missing, inaccessible or malformed preferences fail validation; output from the action is never enough. Alarm and city validators reread UI state.

## Failure modes

- `uiautomator dump` can fail while timer/stopwatch rings animate. Timer and stopwatch final checks avoid it using saved app state. Initial navigation for other actions can still require a readable UI tree; an already-running stopwatch is handled without navigation.
- 12 h vs 24 h display depends on the device setting; helpers accept both.
- A city already on the list is not duplicated; the action still succeeds.

- Intent creation still depends on Google Clock selectors during verification; slow rendering or a changed UI can fail. The `nat2` before-arm failure set no alarm within the agent turn budget; it is not evidence of an independent skill validator check.
- Alarm collection has a six-scan limit; a larger list may be incomplete.

## Samsung timer primitives (1.0.3)

start_timer(seconds, app=auto, label=Timer) detects installed Samsung/Google variants. Samsung supports the duration picker only: custom labels fail, and an existing active timer is preserved. Open SHOW_TIMERS, read the three identified numberpicker_input fields, adjust their adjacent increment/decrement buttons, then reread the requested duration before Start. Validate both foreground timer service and Pause. Use the scoped non-idling snapshot while the countdown runs; never ordinary uiautomator dump.

cancel_timer(app=auto) is Samsung-only: use the visible Cancel/Dismiss/Stop control and verify no active timer service remains. get_timer_state(app=auto) is Samsung-only and returns active, including paused timers; it does not promise remaining time. These actions never navigate to alarms. Google-only legacy actions remain separate.

### `cancel_timer(app=auto)`

Samsung only. Read the visible countdown with the scoped snapshot, tap its Cancel/Dismiss/Stop control, and verify the timer notification service is no longer active. Do not send SHOW_TIMERS while a timer is running: Samsung opens an add-timer picker instead of the active countdown. A current visible cancellation control takes precedence over a lagging service report.

### `get_timer_state(app=auto)`

Samsung only. Return active from the timer and timer-notification foreground services. A paused timer remains active; the state does not promise a remaining duration. No alarms or private app files are read.
