# Badges spec

Status: DRAFT spec for the hub maintainer (data) and hub-web (rendering). Only the Founding Contributor badge is specified in full here; track medals and tiers follow `docs/community/contributor-ladder.md` and synthesis D3.

## Founding Contributor

### Purpose

Reward the people who show up before the hub is proven. Scarce by construction (the GitHub Arctic Vault pattern): a fixed count, numbered, never reissued.

### Eligibility

An account earns Founding Contributor #N when **all** of these are true:

1. It reaches the **Contributor** tier (any track; see the ladder) for the first time.
2. That moment falls inside the window `[LAUNCH_DAY 00:00 UTC, LAUNCH_DAY+45 23:59 UTC]`.
3. Fewer than 100 Founding badges have been issued.
4. The account is at least 14 days old at the qualifying moment, or the badge is held pending until it is (same tenure rule as verification points). Held badges keep their number.

Core team members and fleet bot accounts are not eligible. Seed members invited during prep (L-10 to L-1) are eligible but their qualifying moment is clamped to LAUNCH_DAY, ordered by their real timestamp.

### Numbering

- Number = rank of the qualifying event timestamp among all eligible events, ascending, starting at 1.
- The qualifying event is the merge time of the PR that completed the last Contributor requirement (for Helper medals, the time the helpful mark was recorded).
- Ties (same second) break by GitHub user id ascending.
- Numbers are assigned by a deterministic script, not by hand, so anyone can recompute them from the public merge history.

### Revocation

- A badge is revoked only for a confirmed gaming or safety case that removed the credits needed for Contributor.
- A revoked number is **not reissued** and not shifted. The list shows "#37 (revoked)" without the account name. This keeps every other holder's number stable.

### Data

`skillhub/community/founding.json` (generated, never hand-edited; path is a proposal for the hub maintainer):

```json
{
  "window": {"start": "<LAUNCH_DAY>T00:00:00Z", "end": "<LAUNCH_DAY+45>T23:59:59Z"},
  "cap": 100,
  "issued": [
    {"n": 1, "github": "alice", "github_id": 123456, "qualified_at": "2026-10-19T14:02:11Z", "track": "verifier", "status": "active"},
    {"n": 2, "github": "bob", "github_id": 234567, "qualified_at": "2026-10-19T16:40:03Z", "track": "author", "status": "pending_tenure"}
  ]
}
```

`status`: `active`, `pending_tenure`, `revoked`.

### Display

| Surface | Rendering |
|---|---|
| Profile and author page | Badge chip "Founding #N" next to the tier badge; tooltip "One of the first 100 contributors to Ghost Skill Hub" |
| Skill cards | Not shown. Badges describe people, not skills. |
| Leaderboard | Small "F" marker after the handle, tooltip with number |
| Discord | Role `Founding Contributor` (one role, no per-number roles); number shown in the bot's tier-up post |
| Embeddable | `{HUB_URL}/badges/founding/<github>.svg`, shields-style, label "Ghost Skill Hub", message "Founding #N" |
| All Contributors wall | Tagged with the `founding` key |

Visual: monochrome ghost glyph with the number set in tabular figures. Same badge for #1 and #100: the number is the only difference. No gold, silver, bronze variants. Must pass WCAG AA contrast in light and dark themes. hub-web owns the final SVG; no binary assets in `site/public` (vercel bandwidth trim in progress).

### Announcements

- Bot posts in #showcase on each issue: "@user is Founding Contributor #N. Welcome."
- A weekly post reports the running count.
- Window close (L+45 or #100) gets one #announcements post with the full list.

### Edge cases

| Case | Rule |
|---|---|
| Account renamed on GitHub | Keyed by `github_id`; handle refreshed on next build |
| Two accounts, one person | One badge per human; the later one is revoked if a curator confirms duplication |
| Contributor reached via held runs that clear after the window | Qualifying time is when the account actually met the requirements, so it counts if that was inside the window, even if the hold released later |
| Window ends with fewer than 100 | No more are issued. Scarcity is the point. |
| Season scoring change moves someone below Contributor | Badge stays. Tiers and badges never decay. |
