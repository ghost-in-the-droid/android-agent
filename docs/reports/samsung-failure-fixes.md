# Samsung showcase failure fixes

Cross-device notes for the Calculator, Clock, Markor, Tasks and Pro Expense skills: what failed on a Samsung phone, and what changed.

> **Scope note:** the pass counts below are historical sequential-run outcomes. In that matrix app data was not cleared per action and capture started after launch, so read, list and complete actions inherited earlier setup and persistent-state validators could accept pre-existing data. Do not read them as isolated-run validation, and the earlier "clean-run" compatibility claim is withdrawn. A later isolated matrix (app data cleared before every action) replaced it.

**Samsung: 10/21 actions passing before the fixes, 21/21 after. Emulator: 20/21 before, 21/21 after.** All 11 initial Samsung failures pass now, and no previously passing emulator action regressed. Contacts was not part of this matrix.

## Before and after

| Skill | App version | Samsung before → after | Emulator before → after |
| --- | --- | --- | --- |
| ghost/calculator | 1.4.0 | 3/4 → 4/4 | 4/4 → 4/4 |
| ghost/clock | 7.4 | 2/5 → 5/5 | 4/5 → 5/5 |
| ghost/markor | 2.16.1 | 3/5 → 5/5 | 5/5 → 5/5 |
| ghost/tasks | 15.12 | 2/4 → 4/4 | 4/4 → 4/4 |
| androidworld/pro-expense | 1.0.0-beta05 | 0/3 → 3/3 | 3/3 → 3/3 |

The only emulator baseline failure was `clock/add_world_city`, after a running stopwatch prevented an idle UI dump.

| Device | OS | Screen | Density | Locale |
| --- | --- | --- | --- | --- |
| Samsung SM-A037F | Android 13 | 720×1600 | 300 | en-GB |
| Google SDK x86_64 emulator | Android 13 | 1080×2400 | 420 | en-US |

## Root causes and fixes

- **Calculator:** the unit picker can render late, and native menu rows carry Android resource IDs. Selection now waits for the real menu, matches the requested unit precisely, and retries opening only when the menu is still absent.
- **Clock:** alarm-card detection assumed an 800-pixel minimum width, while this Samsung screen is 720 pixels wide. Card containment and scrolling now use measured bounds. Samsung cannot read Clock's private preferences, so a bounded, Clock-only accessibility snapshot checks a matching timer's decreasing countdown and an increasing stopwatch (root-readable preferences remain authoritative). Expired timers also prevent ordinary idle dumps on other tabs; Clock navigation and visible-state validators use that snapshot. Saved cities must appear on the city-list screen, not merely in search results.
- **Markor:** Samsung's keyboard can move the new-file dialog, redirecting a tap into the filename-format field, and early characters can be lost. The helper now requires fresh native bounds, confirmed name-field focus, and exact readback before creation, and retries only the unsaved name. Notebook listing deduplicates title/description representations of the same file. Repeated launches also trigger a rating dialog; a specific detector declines it.
- **Tasks:** Samsung omits the AOSP pinned-notification dump field. Unknown state still fails closed unless focus and fresh accessibility/window evidence establish an unobscured target. Native dumps omit Compose's Save control, so the fallback checks the focused Tasks window and every higher visible window before accepting the same freshly read control.
- **Pro Expense:** an unrooted Samsung has no readable SQLite ledger. The fallback reopens persisted entries, reads name, amount, note and the checked category, then leaves without pressing UPDATE. Native XML retains the checked state omitted by Portal conversion. Oversized inputs are rejected before writing; the app truncates names at 20 UTF-16 code units, notes at 100 and amount text at 10 characters.

The optional `Device.dump_xml(use_portal=False)` path preserves native package and checked attributes for validators. Default navigation behavior is unchanged.

## Regression checks

Each fix was preceded by a failing focused test.

| Area | Regression test | Fix |
| --- | --- | --- |
| Unit picker | `test_unit_picker_waits_for_dialog_and_accepts_identified_options` | [calculator helper](../../skillhub/ghost/calculator/helpers.py) |
| Narrow alarms / animated Clock | `test_clock_reads_enabled_alarm_on_both_screen_widths`, `test_clock_real_device_reads_app_scoped_snapshot_without_idle_dump` | [Clock helper](../../skillhub/ghost/clock/helpers.py) |
| Filename focus | `test_markor_name_focus_is_required_before_any_text_input`, `test_markor_filename_uses_fresh_native_field_when_portal_lags` | [Markor helper](../../skillhub/ghost/markor/helpers.py) |
| OEM / Compose guard | `test_tasks_compose_target_needs_unobscured_focused_window` | [Tasks helper](../../skillhub/ghost/tasks/helpers.py) |
| Saved expense state | `test_expense_unrooted_editor_reads_persisted_fields_and_checked_card` | [expense helper](../../skillhub/androidworld/pro-expense/helpers.py) |

Additional tests reject static or increasing timer countdowns, wrong or ambiguous timer cards, unreadable snapshots, off-screen or foreign nodes, notification overlaps, oversized expense fields, mismatched persisted fields, search results mistaken for saved cities, and duplicate notebook rows. Adding an existing city is a no-op; city navigation is restored after timer interruptions.

## Evidence

The final matrix used complete per-skill replays after the last implementation changes. All 42 selected run records are signed, accepted by the production verifier, bound to current skill contents and non-simulated. Thirty-six are author self-runs; six Pro Expense records are maintainer verifications. **Independent coverage credit is zero.** Each skill has measured Android 13 Samsung and emulator cells; older unbound or stale evidence stays excluded by the normal registry rules.

All 21 actions passed on both the Samsung phone and the emulator in that matrix. Demo clips were checked frame by frame with OCR for forbidden patterns (388 frames, zero hits) before any public use. Presentation edits mask the top and bottom edge strips, mute audio, cap resolution at 360×720 and speed up captures longer than 28 seconds; they add no replay credit.

Tests used only synthetic data (short expense names, throwaway notes and alarms). Selected phone replays reset only the test state of the freshly installed demo apps; no personal app data was touched. The same already-cached APKs from public sources (for example F-Droid for `org.fossify.math` 1.4.0) were reused, and each demo app was uninstalled afterwards.

## Gates

| Check | Result |
| --- | --- |
| Full Python test suite at the time | 1,674 passed, 10 skipped |
| Frozen supply-chain evaluation | 20/20 bad cases caught; 2/2 controls accepted |
| `ruff check` on touched Python files | clean |
| Signature and content audit of the 42 run records | 42/42 accepted and current |
| Registry rebuild (`--no-write`) | measured cells present; zero independent cells |
