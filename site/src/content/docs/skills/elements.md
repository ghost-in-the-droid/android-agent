---
title: "🎯 Elements & Locators"
description: How Ghost skills locate UI elements — the id → desc → text → xpath chain, and when to fall back to coord blind-tap for known-stable landmarks.
---

Every UI interaction in a Ghost skill needs to **find** an element. This page covers the locator model.

---

## The locator chain

Ghost's `tap_element` and `wait_for_element` primitives use a fallback chain, tried in order:

1. **`id:`** — Android resource-id or iOS accessibility-id. Most precise. Changes between app builds.
2. **`desc:`** — content-desc (Android) or accessibility label (iOS). Most stable across app versions.
3. **`text:`** — visible text. Locale-dependent. Weak.
4. **`xpath:`** — full xpath expression. Escape hatch for complex hierarchies (limited support in v2).

First match wins. If no match found → `StepFailedError` with `hint: "consider wait_for_element before this step"`.

```yaml
steps:
  - {action: tap_element, desc: "Send button"}                    # try desc first
  - {action: tap_element, id: "com.whatsapp:id/send"}             # id-based, brittle to app updates
  - {action: tap_element, text: "Save"}                           # text-based, locale-fragile
```

**Best practice**: prefer `desc:` — most stable across app versions + locales. Use `id:` when desc is missing. Use `text:` only when the text is a known-stable UI landmark ("Post", "Send", "Cancel").

---

## Getting locators

Two ways to discover the right locator:

### Live inspection (recommended)

While the app is on the target screen:

```bash
adb -s <serial> shell uiautomator dump --compressed /sdcard/ui.xml
adb -s <serial> pull /sdcard/ui.xml /tmp/ui.xml
grep -oE '(content-desc|resource-id|text)="[^"]+"' /tmp/ui.xml | sort -u
```

Look for a unique attribute on the element you want to tap. Content-desc is best.

### Ghost inspector (via Skill Creator)

```bash
ghost skill mine <skill> --explore   # planned (v1.7); not in v1.6.0
```

BFS walks the app, records every screen, extracts stable locators. Faster than manual inspection.

---

## Coord blind-tap (for known-stable landmarks)

Some elements have NO stable a11y attributes — TikTok's bottom-nav icons are `content-desc="Profile"` (stable, use `desc:`), but the display-name area at the top of the profile page (used to open the account-switcher) has no reliable attribute. In those cases, use empirically-verified coordinates:

```yaml
- {action: tap, x: 972, y: 2214}   # TT Profile bottom-nav, 1080x2400 devices
- {action: sleep, duration_s: 2}
```

**When to use blind-tap**:
- Known-stable landmark whose position doesn't shift across app versions
- No content-desc / resource-id / text is available
- Video-app screens where `uiautomator` can't reach idle (TT/IG/YT autoplay pages)

**When NOT to blind-tap**: modals, dynamic content, small target areas, screens where coords could shift with an app update. Always prefer a11y locators when they exist.

Document your coord choices in the skill's SOFT.md so future adapt passes know what to preserve.

---

## Element filtering by attribute

Currently supported: `id`, `desc`, `text`. Combined filters (find element matching multiple attrs) not yet in v2 — use `xpath:` for complex cases:

```yaml
- {action: tap_element, xpath: "//android.widget.Button[@content-desc='Send' and @clickable='true']"}
```

**Note**: xpath support in v2 is minimal — id/desc/text covers 95% of cases. Extend via `custom_python` if you need more.

---

## Locator patterns per app class

**Native Android apps** (Chrome, Gmail, Instagram):
- Content-desc is usually populated and stable
- Resource-id changes on major app updates
- Text works but is locale-dependent

**React Native / Flutter apps** (many indie apps):
- Content-desc often missing (framework doesn't emit it by default)
- Resource-id often auto-generated hashes → unstable across builds
- Text or coord may be the only viable option → use `screen_hash:` validator to detect drift

**Web-view apps** (banking, some social):
- Locators are actually browser-side — use `url_contains:` validators
- `open_url` + `type_text` into form fields
- iframe elements especially hard to hit — often needs `custom_python` with WebView-JS injection

**Video-autoplay apps** (TikTok, Instagram, YouTube):
- `uiautomator dump` fails to reach idle
- Use blind-tap for bottom-nav / known landmarks
- Dump AFTER navigating to a static page (profile, settings) — that's when a11y is reliable
- `_fast_dump` in the engine handles Portal fallback automatically

---

## Related

- [Creating Skills](/skills/creating-skills/) — full author flow
- [Skill Schema v2 Reference](/api/skill-classes/) — tap_element + wait_for_element specs
- [Execution Engine](/features/skill-execution-engine/) — the fast_dump gotcha, Layer 1-4 popup handling
