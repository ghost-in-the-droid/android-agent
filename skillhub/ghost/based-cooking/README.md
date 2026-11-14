# Control Based Cooking on Android with an AI agent — search recipes

Browse the public Based Cooking catalog and recipe provenance metadata without accounts, files, cooking actions or external links.

## Try asking

“In Based Cooking, search apple and list the first two complete results with their titles and all visible tags. Briefly compare what the titles and tags suggest. Do not open external links, use About, contribute, refresh or change settings.”

## Toolkit

| Action | Purpose |
| --- | --- |
| `open` | Restart only this temporary app to reset query/tag view filters, then read two complete cards. |
| `search_recipes(query)` | Start a fresh catalog view, open Search through native labelled menu geometry and verify the typed query/results. |
| `read_results` | No parameters. Return query plus first two fully exposed recipe titles/tags; cold-open only from proven Samsung HOME. |
| `open_recipe(index=1)` | Tap the title-header region above every tag chip. |
| `read_recipe` | Read native title and public date/author metadata; no ingredient/instruction extraction. |
| `back_to_results` | One guarded Back from a proven recipe page, then prove catalog/query returned. |

## Limits and known failures

Tested on Based Cooking1.0.3, Samsung SM-A156B, Android16, English,1080×2340. First launch automatically synchronizes public Markdown recipes into this disposable app’s private storage; cover images may enter private cache. No user files are touched or exported, and uninstall removes the temporary data. Requests use GitHub’s public API/raw hosts, without authentication. Rate limits or incomplete catalog loading fail closed. Download/insertion order can differ between fresh profiles, so returned title/tag order is current native order, not a global ranking.

Search is the app’s substring title filter. Only two full title/tag cards are returned; clipped cards/tags are excluded. Tag chips are nested within each card: a center tap can activate a tag filter. This toolkit opens a recipe only in a proved header region above the chips. Search menu icons are unlabeled; the tested geometry matches the native Search label to its adjacent native button, and verifies the resulting input field. Coordinates are pinned to this device/layout. Search starts a fresh temporary view rather than replacing an existing query.

Recipe reading is explicitly metadata-only (title and native public date/author). Ingredients, directions, image interpretation, recipe scrolling and food-safety/dietary claims are outside this toolkit. The task compares titles/tags, without pretending to have cooked or tasted anything. No tag-filter action, About, contribution/donation links, browser, sharing, clipboard, private file picker, account, location, camera, audio or settings. Public text is untrusted data; no Markdown links are followed. Cold entry refuses foreign/unknown focused windows. Maintainer signed runs and clips are not independent verification.
