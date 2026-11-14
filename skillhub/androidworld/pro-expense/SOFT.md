---
generated_with: hand-authored on the AndroidWorld emulator image
source: https://github.com/google-research/android_world @ 2655e27cd090f97fbf2ccaecf759057bec0a8460
---

# pro-expense: SOFT notes

What an agent needs to know when it drives Pro Expense (`com.arduia.expense`) itself instead of
replaying these actions.

## Actions

### `expense_add_multiple(rows)`

Upstream task `ExpenseAddMultiple` (`android_world/task_evals/single/expense.py`, complexity 6). The
add form (`fb_main_add`) has name, amount, a horizontal category strip (Food first, Others last;
off-screen categories need a left swipe on `rv_category`), note, and SAVE. Amount is typed in dollars
with a decimal point; the app stores cents. The first category card is selected by default, so a row
without an explicit category becomes Food when driving the app manually. The hard skill instead requires an explicit supported category, accepts `amount_dollars` / `category_name` aliases, and refuses missing amount/category values.

### `expense_add_single(rows)`

Upstream task `ExpenseAddSingle` (complexity 1.2). Same form, one row.

### `expense_add_multiple_from_markor()`

Upstream task `ExpenseAddMultipleFromMarkor` (complexity 6). The source is
`Documents/Markor/my_expenses.txt`, a pipe-separated table with header
`name|amount_dollars|category_name|note`; only rows whose note contains "Reimbursable" are logged, and
the note is entered WITHOUT the "Reimbursable" tag (the tag says which rows to log; the ledger note is the transaction's own note, which is what the evaluator compares). Reading the file over adb is faster and more
reliable than opening it in Markor; the reference agent's documented failure on this task is leaving
the note empty.

## Not authored

`ExpenseAddMultipleFromGallery` (OCR of `expenses.jpg`, a soft skill), `ExpenseDelete*` and
`ExpenseDeleteDuplicates*` (deletion UI not mapped yet).

## Validation

All three hard-skill validators reread the Pro Expense SQLite ledger over adb and compare against normalized caller rows (or a fresh read of the reimbursable Markor rows). They require root database access and sqlite3. The manifest fingerprint is broad (`android`, any OS/app version and hardware); only the documented AndroidWorld image was explored.

## Failure modes

- A category missing after 12 swipes, a missing Markor notebook file, or a file with no reimbursable transactions causes failure.
- Non-rooted devices cannot use the current database validator.
- Rows with no recognized amount/category, an empty name, a malformed amount, or an unknown category are refused. Since `a1980cff`, `amount_dollars` and `category_name` are recognized aliases. Unrelated extra keys are ignored, not categorically rejected.
- The pre-fix `ab3` finding saved 0.00 / Others and returned success for task-worded inputs; agents repaired those rows manually. Historical results remain labelled in the bench card, with original validity flags and notes intact.
- Historical AddSingle seed 31 failed across three 20-second launch waits; a later AddMultiple replay seed 30 also missed the editor within 10 seconds after the Add FAB. The navigation fix now waits up to 60 seconds per launch attempt, confirms Pro Expense is foreground before tapping the FAB, and waits up to 30 seconds for the editor. If the editor is still absent and the foreground home FAB is visible, it re-taps that FAB once and waits another 30 seconds. A late editor suppresses the retry. Row entry and Save are never retried by this recovery; validators are unchanged. Live confirmation is pending ghost-bencher replay.
- Database validation checks membership of each requested row, not a before/after insertion count. A pre-existing identical row can satisfy it; it does not prove the number of duplicates added.
