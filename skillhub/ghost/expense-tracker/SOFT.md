# expense-tracker - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.totschnig.myexpenses` (My Expenses, GPL-3.0, version 4.1.3.1 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- First run: 3 onboarding slides (Next), then the local account `Budget Book` (no account or login). Transaction list: toolbar with the account name and balance, a totals strip (`Income: ...`, `Expenses: ...`, `Transfers: ...` as content-desc), one row per transaction ("note / payee", amount, date), and the new-transaction button (desc `New Transaction (Expense)`).
- New transaction form (ids): `TaType` (expense/income switch), `AmountEditText`, `auto_complete_textview` (payee), `Category`, `Comment` (notes), save button `fab`.
- Everything is local: nothing is sent anywhere.

## Actions

### `add_expense(amount, payee, note)`

New Transaction > type the amount, payee and note > save. Success: a row with that amount appears and the totals change.

### `add_income(amount, payee, note)`

Same form with the Expense/Income switch flipped.

### `list_transactions()`

Parses the visible rows; negative amounts are expenses. Returns `transactions` and `totals`.

### `get_totals()`

Reads the balance in the toolbar and the totals strip.

## Adapting

Money Manager Ex and similar apps share the form-then-list shape; the totals strip ids differ.
