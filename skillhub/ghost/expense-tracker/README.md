# Control My Expenses on Android with an AI agent — track expenses and budgets

**Control My Expenses on Android with an AI agent.** Track your spending on your phone by asking an agent: add expenses and income, list transactions and read totals.

Target search phrase: _AI agent expense tracker Android_

Demo shows: `add_expense (amount=12.50, payee=Bakery, note=lunch)`

> Ghost in the Droid seed skill for My Expenses (`org.totschnig.myexpenses`), a full-featured open-source expense tracker from F-Droid (this skill uses its local default account, no sync). Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `add_expense` | Add an expense to the local Budget Book | `amount`, `payee`, `note` |
| `add_income` | Add an income | `amount`, `payee`, `note` |
| `list_transactions` | Read transactions (note, payee, amount, date) and totals | none |
| `get_totals` | Read balance, income, expenses, transfers | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | add_expense, add_income |
| Primitives | (category/date are left at the defaults) |
| Read state | list_transactions, get_totals |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.totschnig.myexpenses/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/expense-tracker
```

## Use

```bash
ghost skill run ghost/expense-tracker add_expense --param amount=12.50 --param payee=Bakery --device <serial>
ghost skill run ghost/expense-tracker get_totals --device <serial>
```

```python
run_skill(name="ghost/expense-tracker", action="get_totals")
# {"totals": {"account": "Budget Book", "balance": 87.5, "income": 100.0, "expenses": 12.5, "transfers": 0.0}}
```

Try asking: "Add an expense of 12.50 at the bakery for lunch, then show my totals."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), My Expenses 4.1.3.1. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 4.1.3.1 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Category, date and tags are left at the defaults (today, no category): this is a quick-entry toolkit.
- Amounts are in the account currency (euro in the test account); the helper strips the symbol.
- The first-run onboarding slides are clicked through by the open_list subroutine.
- The list shows only the rows that fit on screen.

### Popups and first-run screens handled

- First-run onboarding (3 slides) handled in open_list.
