---
title: "🎨 Style & Theme Guide"
description: "Brand colors, typography, component patterns, and design rules for the Ghost in the Droid docs site and landing page."
---

This guide covers the visual language of Ghost in the Droid. Follow it when touching the Starlight docs site, the landing page, or any public-facing frontend.

## Brand Colors

The single source of truth is **#00e5a0** -- the ghost green. Everything else derives from it.

| Token | Hex | Usage |
|-------|-----|-------|
| `accent` | `#00e5a0` | Primary brand green. Buttons, links, highlights. |
| `accent-dim` | `#00e5a018` | Translucent green for subtle glows and backgrounds. |
| `accent-mid` | `#00e5a040` | Mid-opacity green for hover states and borders. |
| `accent-high` | `#6efcd0` | Light mint green. Badge text, hover accents. |
| `accent-low` | `#052e1e` | Deep forest green. Sidebar active backgrounds, subtle tints. |

### Green-Tinted Gray Scale

Every neutral in the project carries a subtle green wash. This is intentional -- it makes the entire UI feel like it belongs to one brand instead of being generic gray on black. Never swap these for pure grays.

| Starlight Token | Hex | Role |
|-----------------|-----|------|
| `--sl-color-gray-1` | `#e8ede9` | Primary text (light mode headings, dark mode body) |
| `--sl-color-gray-2` | `#bec8c0` | Secondary text, descriptions |
| `--sl-color-gray-3` | `#8a9a8d` | Tertiary text, labels, placeholders |
| `--sl-color-gray-4` | `#4a5c4e` | Borders, dividers, inactive elements |
| `--sl-color-gray-5` | `#2a3a2d` | Card borders, code block borders, separators |
| `--sl-color-gray-6` | `#161e17` | Card backgrounds, raised surfaces |
| `--sl-color-gray-7` | `#0d130e` | Page background (docs), deepest surface |

These are defined in `site/src/styles/custom.css` and apply to the entire Starlight docs site.

## Typography

### Landing Page

- **Headings:** [Outfit](https://fonts.google.com/specimen/Outfit), weight 800. Tight letter-spacing (`-2.5px` on hero, `-1px` on sections).
- **Code / terminal:** [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono), weights 400-500.
- **Body:** Outfit weight 300-400. Line-height 1.6-1.7.

Both fonts are loaded from Google Fonts in the landing page `<head>`.

### Docs Site

The docs site uses Starlight's default font stack (system fonts). Don't add custom font imports to the docs -- the system stack keeps pages fast and consistent with Starlight conventions.

## Dark Theme

Ghost in the Droid is a dark-first project.

- **Landing page background:** `#050505` -- near-black.
- **Docs site:** Uses Starlight's built-in dark mode with our green-tinted gray overrides. There is a custom theme toggle button (`#ghost-theme-toggle`) that replaces the default Starlight theme picker.
- **Dashboard:** `#0a0f0c` -- slightly green-tinted black.

Never use pure white (`#ffffff`) backgrounds. If light mode is needed, keep surfaces tinted. The lightest surface in the system is `gray-1` (`#e8ede9`), which still has a green cast.

## Component Patterns

### Feature Rows (Landing Page)

Features use alternating left-right layout with ghost mascot images:

```html
<div class="feature-row">
  <div class="feature-img">
    <img src="/mascot/12-the-tap.png" alt="Ghost tapping a phone" />
  </div>
  <div class="feature-text">
    <span class="feature-tag">Device Control</span>
    <h3>Possess Any Android</h3>
    <p>Send taps, swipes, and text through ADB. No root required. Pure automation.</p>
  </div>
</div>

<!-- Next row reverses the order -->
<div class="feature-row reverse">
  ...
</div>
```

Rows alternate using the `.reverse` class, which swaps the image and text columns via CSS `order`.

### Terminal Mockup

The landing page hero includes a fake terminal window showing a code snippet:

```html
<div class="terminal">
  <div class="terminal-header">
    <span class="terminal-dot r"></span>
    <span class="terminal-dot y"></span>
    <span class="terminal-dot g"></span>
    <span class="terminal-title">ghost.py</span>
  </div>
  <div class="terminal-body">
    <!-- Syntax-highlighted code using .t-kw, .t-fn, .t-str, etc. -->
  </div>
</div>
```

### CTA Buttons

Two button styles:

```css
/* Primary: solid green background, dark text */
.btn-primary {
  background: var(--accent);
  color: #050505;
  font-weight: 600;
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
}

/* Outline: transparent background, subtle border */
.btn-outline {
  background: transparent;
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
}
```

Primary buttons are for the main call-to-action ("Get Started", "Install"). Outline buttons are for secondary actions ("View on GitHub", "Browse Docs").

### Stat Cards

Used on the Skill Hub page and landing page to show key numbers:

```html
<div class="stats-bar">
  <div class="stat-item">
    <span class="stat-number">47+</span>
    <span class="stat-label">Device Methods</span>
  </div>
  ...
</div>
```

Numbers are `accent` green, labels are `gray-3`.

## Ghost Mascot Usage

The ghost mascot is the soul of the brand. It appears where it makes sense, doing what the feature describes.

### Key Images

| File | Name | Use For |
|------|------|---------|
| `12-the-tap.png` | The Tap | Hero section, device control features |
| `16-the-watch.png` | The Watch | Screen reading, monitoring, scraping |
| `22-forge.png` | Forge | Skill creation, building, crafting |
| `18-the-farm.png` | The Farm | Phone farm, multi-device management |
| `34-stealth.png` | Stealth | Stealth mode, anti-detection |
| `15-the-possess.png` | The Possess | AI agent, automation, possession metaphor |
| `26-the-share.png` | The Share | Skill hub, publishing, community |
| `35-gigachad.png` | Gigachad | Open source, power, freedom |
| `43-wave.png` | Wave | Footer, friendly farewell, CTA sections |

All images live in `/public/mascot/` and are served at `/mascot/<filename>`.

### Placement Rules

- Ghost appears where it **illustrates the feature being described**. The Tap ghost goes next to device control. The Watch ghost goes next to screen reading. Don't use them as decoration.
- **Max 8-10 placements per page.** More than that and the page starts looking like a sticker book.
- Ghost images should **never be bigger than the content** next to them. Max width 280px in feature rows, 120px in empty states.
- **Never animate ghost images.** No CSS animations, no hover transforms beyond a subtle `scale(1.04)` on the parent row. The ghosts are static illustrations.
- Use the numbered asset files from `/public/mascot/`. Don't create new ghost images without checking the existing set first.

## Emoji Convention

- **Every sidebar item** gets a contextual emoji in the label (defined in `astro.config.mjs`).
- **Every page title** in frontmatter gets a leading emoji.
- **Section groups** in the sidebar get emojis too.
- **In body copy**, use a maximum of one ghost emoji per page. Don't scatter emojis throughout paragraphs.

Examples from the sidebar config:

```
🚀 Getting Started
  👻 Introduction
  📥 Installation
  📱 Connect a Phone
📚 Guides
  🎵 TikTok Upload
  🥷 Stealth Mode
```

## Copy Tone

Short punchy sentences. Hacker energy. This is a tool for people who build things, not a SaaS marketing site.

### Ghost Terminology

Use "ghost" metaphors naturally:

- **Summon** -- start the framework, connect a device
- **Haunt** -- automate an app, run a recurring job
- **Possess** -- take control of a device
- **Banish** -- disconnect, stop a job
- **Phantom** -- stealth features, anti-detection

### Writing Angles

- **Angle A (Ghost/Possession):** Use for hooks and feature introductions. "Summon a ghost into your Android." "Possess any device through ADB."
- **Angle D (Resistance/Open Source):** Use for value propositions and differentiators. "No cloud. No API keys. No permission needed." "Your phone. Your rules."

### Do

- Write like you're explaining to a competent developer, not a product manager.
- Be direct. "Install it. Connect a phone. Run a skill." Not "Our streamlined onboarding experience enables seamless device integration."
- Use code examples liberally. Show, don't describe.
- Humor is fine when it lands. Don't force it.

### Don't

- No corporate buzzwords. Never write "leverage", "synergy", "next-generation", "cutting-edge", "seamlessly".
- Don't explain the joke. If "Ghost in the Droid" is a play on "Ghost in the Shell", the reader either gets it or they don't.
- Don't over-hype. "Powerful" is fine once. "Revolutionary AI-powered automation platform" is not.

## What NOT to Do

1. **No CSS animations on ghost images.** The only motion allowed is a subtle `scale(1.04)` on parent row hover. No spinning, bobbing, floating, or pulsing ghosts.
2. **No ghosts as bullet points.** Don't use ghost emojis or tiny ghost images as list markers.
3. **No more than 10 ghost placements per page.** Count them. If you're over 10, cut the weakest ones.
4. **No generic AI slop colors.** No purple-to-blue gradients on white backgrounds. No teal-and-coral palettes. The brand is green on dark. Stick to it.
5. **Don't mix dark-bg and transparent-bg mascot images.** The mascot PNGs are designed for dark backgrounds. If you place one on a lighter surface, check that the edges look clean. Some have dark halos that look wrong on light backgrounds.
6. **Don't add Google Fonts to the docs site.** The landing page uses Outfit and JetBrains Mono. The docs site uses system fonts. Keep them separate.
7. **Don't override Starlight's component styling** unless you have a good reason. The custom CSS in `custom.css` targets specific elements (header, sidebar active state, code blocks). Don't add broad resets or global overrides.

## Related

- [Dashboard Theme Guide](/contributing/dashboard-theme/) -- CSS variables and patterns for the Vue 3 dashboard
- [Dev Setup](/contributing/setup/) -- get the project running locally
- [Code Guidelines](/contributing/code/) -- PR process and code style
