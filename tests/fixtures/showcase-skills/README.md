Offline regression fixtures, 2026-10-23. These are reduced/reconstructed UI shapes
and fake adb outputs based on showcase6-skill-findings.md, not new device captures.
The Markor row description and Clock preference keys/values reproduce the bench runner's
reported API 33 observations. Contacts includes a stale unfiltered search row and
an untyped phone; Calculator combines independently testable display subtrees.
No fixture is live execution or signed evidence.

Pro Expense wait fixtures are synthetic UI timings chosen to exceed the old
10/20-second bounds, based on the manager’s item 6 failure report. They are not
measured device delays. Fake time also exercises one retry and bounded failure.

`tasks-search-keyboard.xml` is the unmodified terminal UI dump from the f3
Tasks search retry on 2026-10-23 UTC (Tasks.org 15.12, Android 13). It shows the corrupted query `bank by` and no rows. The regression
fake reconstructs the preceding `bank` query and one matching row from the
captured runner result; keyboard transitions and swipe effects are simulated,
not additional captured device states.

`tasks-search-expanded.xml` and `tasks-search-collapsed.xml` are unmodified f2
Tasks.org 15.12 captures from brief 3 (2026-10-23 UTC), before and after one
upward list swipe with the keyboard already hidden. The swipe collapses the
search toolbar offscreen without changing the query. The fake switches between
these real layouts to exercise collection followed by independent validation.

`clock-alarm-resolver.xml` is the unmodified f2 API 33 UI capture immediately
after the implicit SET_ALARM intent on fresh Google Clock, 2026-10-23 UTC.
It shows the Clock/Noice resolver; the test simulates intent routing at that
boundary. The resulting delivered-intent state is simulated, not a UI capture.
