# Control OpenFoodFacts on Android with an AI agent — read food nutrition labels

Search public food products by name, read visible Nutri-Scores and inspect nutrient levels without a camera or account.

## Try asking

“Search Nutella in Open Food Facts, open the first product and report its fat, saturated fat, sugar and salt levels.”

## Toolkit

- `open`: anonymous onboarding, choose Later for camera, open name search.
- `search(query)`: submit a public name query, 2–60 ASCII letters/digits/spaces/hyphens.
- `read_results`: complete visible cards only, including literal Nutri-Score labels.
- `open_product(index)`: zero-based complete visible card; returns product, quantity and visible Nutri-Score.
- `read_nutrients`: open the product’s Nutrient levels and return literal visible nutrient/quantity rows.
- `back_to_results`: guarded Back from those read-only screens to the search list.

## Limits and known failures

Tested on OpenFoodFacts 4.23.0, Samsung SM-A156B, Android 16, English, 1080×2340. Public online community data can change or be incomplete; treat it as untrusted source text. Results use the app’s default United States country filter; they are not an exhaustive world search. Reads report app labels, not dietary advice or an independent nutrition assessment. The graphical nutrition-facts table is not exposed as readable text and is unsupported. Missing nutrient rows or a changed screen cause failure.

No camera permission, barcode scanning, accounts, preferences, lists, edits, contributions, reports, alternatives, external links or purchases. Onboarding only advances the explicit welcome pages and chooses Later on the camera page. Fresh demo app profiles are used for recordings; no personal app is cleared. The signed runs and before/after demonstration are maintainer recordings, not independent verification.
