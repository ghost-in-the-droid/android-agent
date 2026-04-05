---
title: "🖌️ Dashboard Theme Guide"
description: "CSS variables, color system, component patterns, and status ghosts for the Vue 3 dashboard."
---

This guide covers the visual system for the Vue 3 + Vite dashboard app (`frontend/`). If you're adding tabs, components, or touching styles, read this first.

## CSS Variables

All dashboard colors are defined in `frontend/src/assets/main.css`. Use these variables everywhere -- never hardcode hex values in components.

| Variable | Hex | Role |
|----------|-----|------|
| `--bg-base` | `#0a0f0c` | Page background. The darkest surface. |
| `--bg-card` | `#141e17` | Card and panel backgrounds. Raised surface. |
| `--bg-deep` | `#060a07` | Inset areas, deeper than base. Used sparingly. |
| `--border` | `#1e2e22` | Default border for cards, dividers, inputs. |
| `--text-1` | `#e8ede9` | Primary text. Headings, important labels. |
| `--text-2` | `#bec8c0` | Secondary text. Descriptions, body copy. |
| `--text-3` | `#8a9a8d` | Tertiary text. Timestamps, hints, placeholders. |
| `--text-4` | `#5a6e5e` | Quaternary text. Disabled states, very subtle labels. |
| `--accent` | `#00e5a0` | Brand green. Active states, primary buttons, links. |
| `--accent-lt` | `#6efcd0` | Light mint green. Hover accents, badge text. |

### Using Variables in Templates

Reference CSS variables via inline styles or `:style` bindings. Don't rely on Tailwind color classes for brand colors.

```vue
<!-- Do this -->
<p style="color: var(--text-2)">Description text</p>
<span :style="{ color: 'var(--accent)' }">Active</span>

<!-- Don't do this -->
<p class="text-green-400">Description text</p>
```

## Component Classes

### Cards

The `.card` class is the workhorse container:

```css
.card {
  background: var(--bg-card);    /* #141e17 */
  border: 1px solid var(--border); /* #1e2e22 */
  border-radius: 12px;
  padding: 16px;
}
```

Usage:

```vue
<div class="card">
  <h3 style="color: var(--text-1)">Card Title</h3>
  <p style="color: var(--text-2)">Card content goes here.</p>
</div>
```

### Stat Cards

Compact number displays used in overview panels:

```css
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  text-align: center;
}
.stat-card h3 { font-size: 24px; font-weight: 700; }
.stat-card p  { font-size: 12px; color: var(--text-3); }
```

Usage:

```vue
<div class="stat-card">
  <h3 style="color: var(--accent)">12</h3>
  <p>Active Devices</p>
</div>
```

### Buttons

Three button variants:

```css
/* Default: dark bg, subtle border, accent hover */
.btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-1);
}
.btn:hover { border-color: var(--accent); }

/* Primary: solid green */
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.btn-primary:hover { opacity: 0.9; }

/* Small variant */
.btn-sm { padding: 4px 10px; font-size: 12px; }
```

Usage:

```vue
<button class="btn">Secondary Action</button>
<button class="btn btn-primary">Run Skill</button>
<button class="btn btn-sm">Small</button>
```

## Tab System

Tabs are defined in `frontend/src/App.vue` as a flat array. The active tab gets an emerald-tinted style.

### Active vs Inactive State

```vue
<button
  :class="activeTab === tab.id
    ? 'border-emerald-500/70 text-emerald-500/80 bg-emerald-500/8'
    : 'border-transparent text-slate-500 hover:text-slate-300'">
  {{ tab.label }}
</button>
```

Active tabs show a green bottom border, green text, and a faint green background. Inactive tabs are slate gray with a lighter hover state.

### Premium Tab Gating

Some tabs are gated behind a premium toggle stored in `localStorage`:

```typescript
const PREMIUM_TABS = new Set([
  'influencers', 'analytics', 'strategies',
  'content', 'generate', 'agent', 'metrics'
])

const showPremium = ref(localStorage.getItem('droidbot-premium') === 'true')
const visibleTabs = computed(() =>
  showPremium.value ? tabs : tabs.filter(t => !PREMIUM_TABS.has(t.id))
)
```

### Adding a New Tab

1. **Add the tab entry** to the `tabs` array in `App.vue`:

```typescript
const tabs = [
  // ... existing tabs
  { id: 'mytab', label: '🔮 My Tab' },
]
```

2. **Create the view component** at `frontend/src/views/MyTabView.vue`.

3. **Import and register** in `App.vue`:

```typescript
import MyTabView from '@/views/MyTabView.vue'
```

4. **Add the conditional render** in the template:

```vue
<MyTabView v-else-if="activeTab === 'mytab'" />
```

5. If the tab should be premium-only, add its ID to `PREMIUM_TABS`.

## Status Ghost System

The dashboard header shows a 36px ghost mascot image that reflects the current system state. It polls two endpoints every 10 seconds.

### How It Works

```typescript
const ghostState = ref<'disconnected' | 'idle' | 'working' | 'error'>('disconnected')

const GHOST_IMAGES: Record<string, string> = {
  disconnected: '/mascot/33-disconnected.png',
  idle:         '/mascot/27-idle.png',
  working:      '/mascot/28-working.png',
  error:        '/mascot/30-error.png',
}
```

### State Machine

| State | Image | Condition |
|-------|-------|-----------|
| `disconnected` | `33-disconnected.png` | No devices returned from `/api/phone/devices`, or fetch fails entirely. |
| `idle` | `27-idle.png` | At least one device connected, no jobs running in `/api/scheduler/queue`. |
| `working` | `28-working.png` | At least one device connected AND a job has `status === 'running'` in the queue. |
| `error` | `30-error.png` | `/api/phone/devices` returns a non-OK response. |

The ghost image sits in the header next to the "Ghost in the Droid" title:

```vue
<img
  :src="GHOST_IMAGES[ghostState]"
  alt=""
  style="width:36px;height:36px;object-fit:contain;transition:opacity 0.3s"
/>
```

Polling starts on mount and clears on unmount. The 10-second interval is hardcoded -- don't make it faster or the server logs fill up.

## Empty States

When a tab has no data to show, display a centered ghost illustration with a short message. This gives the page personality instead of a blank void.

### Pattern

```vue
<div style="display:flex;flex-direction:column;align-items:center;
            justify-content:center;padding:5rem 2rem;text-align:center">
  <img
    src="/mascot/27-idle.png"
    alt="Ghost sleeping"
    style="width:120px;height:120px;object-fit:contain;
           margin-bottom:1.5rem;opacity:0.8"
  />
  <h2 style="font-size:1.5rem;font-weight:700;color:var(--text-1);
             margin-bottom:0.5rem">
    The ghost is sleeping on this one.
  </h2>
  <p style="color:var(--text-3);max-width:400px;font-size:0.9rem;
            line-height:1.6">
    Feature description or status update goes here.
  </p>
</div>
```

### Rules

- Ghost image: **120px** wide, `opacity: 0.8` so it doesn't dominate.
- Pick a ghost that fits the context. Idle ghost for "coming soon" features. Error ghost for failure states.
- Heading: short, personality-forward. "The ghost is sleeping on this one." Not "No data available."
- Description: one or two sentences explaining what the tab will do or what went wrong.
- Optionally include a hint card below the description with a link to relevant docs or a tracking reference.

## Color Matching

The dashboard and docs site share the same green-tinted gray palette. The mapping:

| Dashboard Variable | Docs Equivalent | Shared Hex |
|-------------------|-----------------|------------|
| `--text-1` | `--sl-color-gray-1` | `#e8ede9` |
| `--text-2` | `--sl-color-gray-2` | `#bec8c0` |
| `--text-3` | `--sl-color-gray-3` | `#8a9a8d` |
| `--accent` | `--sl-color-accent` | `#00e5a0` |
| `--accent-lt` | `--sl-color-accent-high` | `#6efcd0` |

If you change a color in `main.css`, open the docs site side-by-side and check that the two still feel like one product. The accent green `#00e5a0` is the single source of truth -- if that ever changes (it shouldn't), it must change in both `frontend/src/assets/main.css` and `site/src/styles/custom.css` simultaneously.

## Tailwind Usage

The dashboard uses **Tailwind CSS 4** via a single import at the top of `main.css`:

```css
@import "tailwindcss";
```

### Guidelines

- **Use Tailwind utilities for layout:** `flex`, `gap-3`, `px-6`, `py-4`, `grid`, `rounded-lg`, etc.
- **Use CSS variables for colors:** Don't use Tailwind's built-in color classes (`text-green-400`, `bg-slate-800`) for brand colors. Use `style="color: var(--accent)"` instead. This keeps the palette centralized and avoids drift.
- **Exception:** The tab active state uses `emerald-500/70` and `slate-500` Tailwind classes because they're close enough to the brand palette for that specific UI element. Don't expand this pattern to other components.
- **Responsive:** Use Tailwind breakpoints (`sm:`, `md:`, `lg:`) for layout shifts. The dashboard is primarily a desktop tool, but tabs should wrap gracefully on smaller screens (`flex-wrap` is already on the tab bar).

### Example: Combining Tailwind Layout with CSS Variables

```vue
<div class="flex items-center gap-3 px-4 py-3 rounded-lg"
     style="background: var(--bg-card); border: 1px solid var(--border)">
  <span class="text-sm font-semibold" style="color: var(--text-1)">
    Device Connected
  </span>
  <span class="text-xs" style="color: var(--accent)">Online</span>
</div>
```

## Related

- [Style & Theme Guide](/contributing/style-guide/) -- brand colors and patterns for the docs site and landing page
- [Dev Setup](/contributing/setup/) -- get the project running locally
- [Code Guidelines](/contributing/code/) -- PR process and code style
