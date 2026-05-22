# Kickoff: Build Demo Night Presentation for Ghost in the Droid

## Your task
Build a polished slide deck for a 3-minute live demo presentation at **w3hub Berlin "Bringing SF to Berlin" demo night**.

The presenter is CKL (Christian). He goes **first**. Audience: Berlin tech/startup crowd, dev-friendly.

---

## Step 1 — Read these files first

**Content / script:**
- `docs/HUMAN/notes.md` — full slide-by-slide script and story notes from CKL
- `docs/HUMAN/presentation/script.md` — refined version
- `docs/ARCHITECTURE.md` — understand the actual system
- `docs/TOOLS.md` — for accurate MCP tool count and real tool names
- `docs/FEATURE_SUMMARY.md` — for accurate feature list

**Brand / visual identity — read these before touching any design:**
- `../../../docs/marketing/BRAND.md` — colors, fonts, voice, tone
- `../../../docs/marketing/MASCOT_PROMPTS.md` — mascot character spec
- `../../../docs/marketing/assets/mascot/clean/CATALOG.md` — what mascot images already exist

Read all of these before producing anything. Get the facts right.

---

## Step 2 — Build the slides

**Format:** **Slidev** (`slides.md`) — Vue/Vite based, Markdown-driven, gorgeous dark themes.
Init with `npm init slidev@latest` if not already set up, or just produce the `slides.md` file directly.

**Output location:** `docs/HUMAN/presentation/`

---

## Slide structure (6 slides, ~3 min total)

### SLIDE 1 — Hook / Intro (0:00–0:35)
- "I hate manual work."
- PussyBot story: "Ten years ago I automated my dating life. All my dates came from a bot. There may or may not be legal implications."
- Transition: "If I can automate that... why not every app?"
- **Visual:** [IMAGE PLACEHOLDER — funny meme: "Why not automate all the apps"]
- CKL will provide the meme image later. Use placeholder text in the slide for now.

### SLIDE 2 — What is Ghost in the Droid (0:35–0:50)
- "Ghost in the Droid gives your AI agents an Android body."
- "Exposes a local MCP with [TOOL COUNT] tools to take full control of any Android device."
- Key 3-word pitch: No root. No APIs. No scripts.
- **Visual:** Ghost logo / product screenshot — [IMAGE PLACEHOLDER]

### SLIDE 3 — Skills / MCP grid (0:50–1:15, stays up during demo start)
- Title: "What can it do?"
- Grid of MCP tool names / skill categories — pull real names from `docs/TOOLS.md`
- This slide is WALLPAPER while the demo spins up — scannable at a glance
- **Visual:** Clean icon grid or tag cloud of capabilities

### SLIDE 4 — Tech specs (1:15–2:05, wallpaper during killer demo)
- This is background while the live demo runs — keep it readable at a glance
- Tightest possible bullets (6 max):
  - No root, no API, no scripts — GUI like a human
  - MCP with [X] tools: screenshot, OCR, DOM tree, tap, scroll, type...
  - Any inference engine: Claude, Ollama, llama.cpp, VLLM, Hermes, OpenClaw
  - 20 tok/s on Gemma 4 2B Q4KM on a 10-year-old Android (custom Vulkan drivers)
  - Multi-device management + job scheduler built in
  - Apache 2.0 — 4M Play Store apps. Not the ones with APIs. **ALL of them.**
- **Visual:** [IMAGE PLACEHOLDER — multi-phone setup / 6-screen rig photo] — CKL will add

### SLIDE 5 — Contribute (2:05–2:25)
- Skill Hub: reusable, versioned, shareable skills
- Version format: `android-version · phone-id · app-version`
- "Contribute once. Runs everywhere. Join the swarm."
- Apache 2.0, link to GitHub

### SLIDE 6 — Outro / What else I'm building (2:25–3:00)
- 4 projects, one line each + image placeholder per project:
  - **TailFrame** — "This is my cat. This is his app. It could be your pet's app."
  - **GladOS** — "My personal AI OS. My own version of Hermes."
  - **Agent Overflow** — "Marketplace for scientific agents."
  - **JSL** — "VLMs, tune, quantize and benchmark on multimodal tasks."
- Big QR code → ckl.wtf
- Text: "Come find me after."

---

## Style guidelines

Follow the brand guide (`marketing/BRAND.md`). Key rules:
- Dark background (black or very dark grey) — demo nights are dim rooms
- Use brand accent colors exactly as specified in BRAND.md
- Large text, minimal words per slide — people are watching a phone, not reading
- No bullet-point walls — max 6 items per slide, ideally 3-4
- Slide numbers in corner

**Mascot usage:**
- SVGs are at `docs/marketing/assets/mascot/svgs/` — use these directly, no background issues
- PNG variants at `docs/marketing/assets/mascot/clean/` — check CATALOG.md for which emotion fits which slide
- Use the mascot character on slides where it adds personality (hook, contribute, outro) — not on data-heavy slides
- Mascot SVGs render natively without square white backgrounds — prefer SVG over PNG wherever possible
- If you need a new mascot pose/variant not in the assets, generate it using the prompts in `marketing/MASCOT_PROMPTS.md` via the GPT Image API (gpt-image-1) and save to `docs/marketing/assets/mascot/new-stuff/`

---

## What CKL will add later
- Meme image (slide 1)
- Multi-phone setup / 6-screen rig photo (slide 4)
- Per-project images (slide 6)
- QR code for ckl.wtf (slide 6)

Mark all of these clearly as `[IMAGE PLACEHOLDER: ...]` so he can drop them in.
Everything else (mascot, brand assets) should be wired up by you directly.

---

## Definition of Done
- [ ] `slides.md` (Slidev) exists in `docs/HUMAN/presentation/`
- [ ] All 6 slides present, correct order, correct timing notes in speaker notes
- [ ] Real tool/feature data pulled from `docs/TOOLS.md` and `docs/FEATURE_SUMMARY.md`
- [ ] Brand colors and fonts match `marketing/BRAND.md`
- [ ] Mascot SVGs used on personality slides (hook, contribute, outro)
- [ ] All image placeholders clearly marked for CKL to drop in
- [ ] Readable on a projector at a glance (large font, dark bg, minimal text)
- [ ] No spelling errors in the spoken script annotations
