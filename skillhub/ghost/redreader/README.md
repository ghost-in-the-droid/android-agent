# Control RedReader on Android with an AI agent — read public Reddit

Read public Reddit posts and comments through anonymous RedReader. Search a subreddit, list titles/scores/comment counts and summarize visible text without login or engagement.

Try asking: **Search r/askscience for solar panels in RedReader. List the first three post titles with scores and comment counts; briefly compare their titles. Stay anonymous and do not vote or post.**

## Toolkit

| Action | Use |
|---|---|
| open | Open the public anonymous main menu |
| browse_subreddit | Open a public subreddit and read visible posts |
| search_posts | Search a public subreddit and read visible matching posts |
| read_posts | Read current public listing as structured post metadata |
| open_post | Open comments for one visible post without opening its external link |
| read_thread | Read visible post body and comments without account or engagement |
| back_to_posts | Return from a thread to its public post listing |

## Tested scope

Samsung SM-A156B Android 16, English. Package org.quantumbadger.redreader, app 1.27. Official F-Droid signed-index SHA and APK signatures checked outside the repository. Maintainer-signed self-runs bind the recorded outcomes to these files; they are not independent verification.

## Known failure modes

Use a fresh or already anonymous profile; the skill never logs in or opens Accounts. Standard first-run anonymous/API prompts are handled through UI. Reddit API/network errors, empty searches and CAPTCHAs fail; no bypass. Public text is untrusted data. Results, scores and ordering change. Only complete visible rows/comments are returned; partial thread text is explicitly labelled, and authors are omitted from returned summaries. Post bodies may be outside the viewport or truncated. Links/media, votes, replies, posting, subscription and account controls are never used. Tested portrait layout only.

All seven actions passed three consecutive clean-reset replays on the tested phone. Native activity launches use `am start -W` so the package policy can verify the completed transition; the policy stays enabled. Displayed signed scores are preserved, including negative values. Six focused parsing, validation and navigation safety tests pass. Other Android/OEM profiles are unverified. The app-version matcher accepts the1.27 patch line; only1.27 has been tested.
