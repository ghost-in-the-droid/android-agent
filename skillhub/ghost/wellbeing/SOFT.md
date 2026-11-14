# wellbeing - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another build.

**Package**: `com.google.android.apps.wellbeing` (Digital Wellbeing & parental controls, preinstalled)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Digital Wellbeing 1.6, en-US, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- The launcher entry is hidden on this build; the overview is `com.google.android.apps.wellbeing/.settings.TopLevelSettingsActivity` (exported, started directly). It shows `id/today_screen_time` (`1 hr, 5 min`), the pie chart description (`Phone used for 1 hour, 5 minutes today`), `id/unlock_count` (`-` when unknown), `id/notification_count`. The chart centre `id/pie_chart_center_labels_container` (`Go to dashboard`) opens the Dashboard; the Dashboard activity itself is not exported.
- Dashboard rows: `id/app_label`, `id/app_time` (`9 minutes`), and `id/limit_button` whose description holds the timer state: `No timer set for Clock`, `30 minutes set for Clock`, `1 hr, 30 min set for Clock`, or `Can't set timer` (system apps such as Settings). The button's description uses the app's full name (`Breezy Weather`) while the label may be shorter (`Weather`), so rows are matched by position.
- Timer dialog: two `android:id/numberpicker_input` pickers (hours, minutes in 5-minute steps); tapping the item below/above the centre steps by one. `OK` is `android:id/button1`; with a timer set the dialog also offers `id/delete_limit_button` (`Delete timer`).

## Actions

### `get_screen_time_today()`

Overview: returns `today: {screen_time, summary, unlocks, notifications}`.

### `list_app_usage(limit)`

Dashboard rows while scrolling: `apps: [{app, used, timer, timer_allowed}]`.

### `set_app_timer(app, minutes)`

Find the row, tap its timer button, step both pickers to `minutes` (multiple of 5), OK. Success: the button description converts back to the same number of minutes. When the timer runs out the app is paused until midnight, so prefer generous values and `remove_app_timer` when done.

### `remove_app_timer(app)`

Open the row's timer dialog and tap `Delete timer`; no-op when no timer is set. Success: the row shows `No timer set for ...`.

## Failure modes

- Apps that were not used today are not listed and cannot get a timer from the Dashboard.
- Pixel builds with Bedtime and Focus mode set up show more cards on the overview; the ids above are unchanged.
