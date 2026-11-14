# Control Pro Expense on Android with an AI agent — track expenses

Pro Expense (`com.arduia.expense`) bookkeeping as deterministic hard skills for the AndroidWorld
Expense tasks. Status: **active** for the three add tasks; the delete and de-duplicate tasks and the
gallery (OCR) variant are not authored yet.

## Attribution

Task names, goals and the evaluator contract come from
[google-research/android_world](https://github.com/google-research/android_world) at commit
`2655e27cd090f97fbf2ccaecf759057bec0a8460`, licensed under Apache-2.0 (see `LICENSE`). The UI steps were
written from the running app on the AndroidWorld Pixel 6 / API 33 image, never from the evaluator
internals; the skill takes the task's values as params and hard-codes nothing from a task instance.

## Actions

| Action | AndroidWorld task | Params |
|---|---|---|
| `expense_add_multiple` | ExpenseAddMultiple (complexity 6) | `rows`: JSON list of `{name, amount, category, note}` |
| `expense_add_single` | ExpenseAddSingle (complexity 1.2) | `rows`: one-element list |
| `expense_add_multiple_from_markor` | ExpenseAddMultipleFromMarkor (complexity 6) | none; reads `Documents/Markor/my_expenses.txt` and logs the rows whose note says Reimbursable |

`amount` is dollars as text (`"12.50"`); the app stores cents. `amount_dollars` and `category_name` (the AndroidWorld
task wording) are accepted as aliases, and a row with no amount or no category is refused rather than saved as 0.00 / Others. `category` is one of Others, Income,
Food, Housing, Social, Entertainment, Transportation, Clothes, Health Care, Education, Donation.

```bash
ghost skill run androidworld/pro-expense expense_add_multiple --device <serial> \
  --param 'rows=[{"name": "Train ticket", "amount": "23.40", "category": "Transportation", "note": "Client visit"}]'
```

## How it works

1. `open_pro_expense` launches the app and finishes the first-run language and currency pages when
   they show.
2. `helpers:add_rows` taps the add button for every row, types name and amount, picks the category on
   the horizontal strip (scrolling it into view), types the note and saves.
3. The end-state validator reads the app's own SQLite table over adb (`adbd` runs as root on the
   emulator image) and checks that every requested row is present with the exact cents, category id and note, normalizing the caller input again rather than trusting the returned rows. If SQLite is inaccessible, it opens saved entries from today's expense log and independently reads the existing editor's full name, amount, note and checked category. It leaves that editor without pressing UPDATE.

## Bench

`ghost skill bench androidworld/pro-expense --androidworld ExpenseAddMultipleFromMarkor --bridge-cmd "<aw_bridge command>"`
replays the action on an AndroidWorld emulator and lets AndroidWorld's `task.is_successful` judge it;
results land in `bench/androidworld.json` (display only) and in signed run artifacts with a `bench` block.

## Failure modes

- The category strip did not scroll to the wanted name within 12 swipes: the strip order changed with
  an app update; fix `CATEGORIES` in `helpers.py`.
- `my_expenses.txt is not in the Markor notebook`: the Markor file path differs from AndroidWorld's
  `Documents/Markor`; pass the task through the bench so `initialize_task` writes it.
- The unrooted UI validator searches at most eight log screens and twelve category-strip views. Missing entries, ambiguous/unchecked categories, unexpected screens or mismatched stored fields fail validation.
- App field limits are checked before row entry: name 20 characters, amount 10 characters, note 100 characters. Oversized inputs are rejected instead of silently truncated by Android.

- Rows with no recognized amount/category, an empty name, a malformed amount, or an unknown category are refused. Since `a1980cff`, `amount_dollars` and `category_name` are recognized aliases. Unrelated extra keys are ignored, not categorically rejected.
- The pre-fix `ab3` finding saved 0.00 / Others and returned success for task-worded inputs; agents repaired those rows manually. Historical results remain labelled in the bench card, with original validity flags and notes intact.
- Historical AddSingle seed 31 failed across three 20-second launch waits; a later AddMultiple replay seed 30 also missed the editor within 10 seconds after the Add FAB. The navigation fix now waits up to 60 seconds per launch attempt, confirms Pro Expense is foreground before tapping the FAB, and waits up to 30 seconds for the editor. If the editor is still absent and the foreground home FAB is visible, it re-taps that FAB once and waits another 30 seconds. A late editor suppresses the retry. Row entry and Save are never retried by this recovery; validators are unchanged. Live confirmation is pending ghost-bencher replay.
- Database validation checks membership of each requested row, not a before/after insertion count. A pre-existing identical row can satisfy it; it does not prove the number of duplicates added.

## Compatibility

The broad manifest fingerprint for `com.arduia.expense` is not proof of general compatibility. Rooted AndroidWorld uses SQLite validation; unrooted Samsung Android 13 uses the saved-entry UI fallback. Both checks verify row membership rather than insertion counts. Consult current digest-bound evidence and the device grid for exercised app versions, screens and locales.
