---
title: "Ghost 1.6: skills that cut tokens by 90%"
description: "117 skills for 113 Android apps, replayable actions, and a median 90% reduction in agent tokens across 99 skills, with the evidence and the failures on the record."
---

Ghost 1.6 cuts agent tokens by a median of **90%** when your agent replays a skill instead of working through the app again. That's about **10x fewer**, measured across 99 skills, and the tasks finished a bit faster too.

The rebuilt skill system ships **117 skills for 113 Android apps**, up from the 3 skills in the previous hub. Your agent learned an app once. Now it doesn't have to relearn the same screens on every run.

Ghost in the Droid gives your agent a phone to operate. It reads the screen, taps, swipes, and types. GHOST is the agent haunting that phone, and this release gives it a library of routes to call when the way through an app is already known.

<video src="/media/release/ghost-1-6-trailer.mp4" controls playsinline preload="metadata" style="width:100%;border-radius:8px" aria-label="Ghost in the Droid 1.6 announcement trailer"></video>

## Hard skills replay the route, soft skills keep the guide

A **hard skill** is an executable YAML action pinned to an OS version, device, and app version. It replays without an LLM, so your agent calls the action instead of reasoning through each tap again.

The pinning matters. A workflow recorded against one app layout can break when the layout changes, and a successful run on the author's phone doesn't show that the same action works on yours.

Every skill also ships a **soft skill**: a plain-language `SOFT.md` guide to completing the task. When no hard skill matches your setup, your agent reads that guide, operates the app itself, and can then create a fitting hard skill for your phone.

In short, the hard skill executes a known route, and the soft skill explains the task when your agent has to find its way.

## How many tokens do hard skills save?

A median of 90%. Every one of the 99 skills with a before/after recording ran the same task twice on a real phone, with the same prompt and the same model (Haiku 5.5): once without the skill, once with it. The median token reduction was **90%**, a **10.2x** reduction factor (95% interval **6.7x to 11.8x**). In 4 of the 99, the skill used more tokens than driving by hand. I'd rather you hear that from us.

The task also finished faster, a median **1.24x**.

A separate controlled run on 39 actions, one phone, repeated with and without the skill, points the same way: a median **85%** fewer tokens.

<figure class="token-bars" style="margin:1.5rem 0">
<svg viewBox="0 0 560 300" role="img" aria-label="With vs without a skill, median over 99 skills, without = 100%. Tokens 10% (90% fewer). Time 81% (19% less). Tool calls 29% (71% fewer)." style="width:100%;height:auto;font-family:inherit;color:inherit">
<g fill="currentColor" font-size="14">
<text x="0" y="20" font-weight="700" font-size="15">With vs without a skill (without = 100%)</text>
<text x="0" y="68" font-weight="600">Tokens</text>
<text x="110" y="52" font-size="12" opacity=".75">without</text>
<rect x="170" y="40" width="230" height="16" rx="3" fill="currentColor" opacity=".35"/>
<text x="408" y="53" font-size="13">100%</text>
<text x="110" y="78" font-size="12" opacity=".75">with</text>
<rect x="170" y="66" width="22.5" height="16" rx="3" fill="#3fb68b"/>
<text x="200.5" y="79" font-size="13" font-weight="700" fill="#3fb68b">10% (90% fewer)</text>
<text x="0" y="143" font-weight="600">Time</text>
<text x="110" y="127" font-size="12" opacity=".75">without</text>
<rect x="170" y="115" width="230" height="16" rx="3" fill="currentColor" opacity=".35"/>
<text x="408" y="128" font-size="13">100%</text>
<text x="110" y="153" font-size="12" opacity=".75">with</text>
<rect x="170" y="141" width="185.8" height="16" rx="3" fill="#3fb68b"/>
<text x="363.8" y="154" font-size="13" font-weight="700" fill="#3fb68b">81% (19% less time)</text>
<text x="0" y="218" font-weight="600">Tool calls</text>
<text x="110" y="202" font-size="12" opacity=".75">without</text>
<rect x="170" y="190" width="230" height="16" rx="3" fill="currentColor" opacity=".35"/>
<text x="408" y="203" font-size="13">100%</text>
<text x="110" y="228" font-size="12" opacity=".75">with</text>
<rect x="170" y="216" width="65.8" height="16" rx="3" fill="#3fb68b"/>
<text x="243.8" y="229" font-size="13" font-weight="700" fill="#3fb68b">29% (71% fewer)</text>
<text x="0" y="280" font-size="11.5" opacity=".7">Median over 99 skills, Haiku 5.5, real phones, same prompt with and without the skill.</text>
</g></svg>
</figure>

The Calculator demo shows it on one task: **92% fewer tokens** with the skill.

<video src="/media/release/calculator-comparison.mp4" controls playsinline preload="metadata" style="width:100%;border-radius:8px" aria-label="Calculator skill demo: same prompt with and without the skill, 92% fewer tokens"></video>

## What are soft skills for?

A soft skill isn't a shortcut. It's the fallback, and the starting point for a new hard skill.

When no hard skill matches your phone, Android version or app version, your agent reads the skill's `SOFT.md`: what the task is, which screens to expect, where the traps are. It drives the app by hand and still gets the job done. That run costs tokens like any agent run. Then your agent can write down the route it found as a new hard skill for your setup, following the [skill creation guide](/skills/skill-creation-guide/). From then on, that action replays without an LLM.

Soft skill to find the route once, hard skill to replay it. See [Hard vs Soft skills](/skills/overview/#hard-vs-soft-skills) in the docs.

## Will it work on my phone?

Maybe, and the honest answer is a matrix. A skill is pinned to the setups it was recorded on, so the Hub now publishes every skill against every phone and Android version it was run on, and how often it worked there, failures included.

| Setup | Skills tested | Runs passed |
|---|---|---|
| Galaxy A03s, Android 13 | 63 | 4,714 / 4,893 |
| Galaxy A15 5G, Android 16 | 38 | 3,648 / 3,656 |
| Emulator, Android 13 | 22 | 167 / 194 |
| Emulator, Android 14 | 20 | 239 / 240 |

Most skills are tested on one setup so far, and 20 run on two or more. A blank cell means not tested yet, not broken. Run a skill on your own phone and your setup gets added. See the full [compatibility matrix](/skills/compatibility/).

## Check the record before you install

The [Skill Hub](https://ghostinthedroid.com/skills/) puts installation and evidence in one place. You can search, install, and update skills from the CLI or through MCP, and before you pick an action you can look at what supports it.

There are demo clips for **99 skills**, plus before/after videos for **99 skills**. A demo shows the action being performed. A comparison shows the same prompt and phone with and without the skill. Watch what it does, then read the evidence behind it.

Each skill has a score from **0 to 100**. Evidence and documentation earn points. Downloads and likes don't.

## When a human has to step in

Some steps need a person. A skill can pause, ask you to handle a checkpoint such as a captcha, and resume afterward.

<video src="/media/hitl/hitl-hcaptcha.mp4" autoplay muted loop playsinline controls preload="metadata" style="width:100%;border-radius:8px" aria-label="hCaptcha demo: the agent fills the form, calls a human for the captcha, then finishes"></video>

So human intervention is part of the workflow. Your agent hands control back when it needs to, then carries on once you've dealt with the checkpoint. We tried it on four captcha demo pages (reCAPTCHA, hCaptcha, BotDetect and MTCaptcha): each time a fresh agent filled the form, called for a human, and finished the job once the captcha was solved. Watch the [four demos](/guides/human-in-the-loop/#demos-four-captchas-one-human) and read [how to run an AI agent with a human in the loop on Android](/guides/human-in-the-loop/).

## Try it on your phone

Upgrade an existing installation and install the Calculator skill:

```bash
pipx upgrade ghost-in-the-droid
ghost skill install ghost/calculator
```

For an existing legacy skill, use the migration command:

```bash
ghost skill migrate <path>
```

Browse the Hub, check the compatibility information, and look at the recorded runs. Start with an action you can verify yourself, and watch where your setup differs from the recorded one, especially the OS, device, and app version.

## What comes next

What we need most is independent evidence: people running skills on their own phones and telling us what happens.

Skill mining and automatic adaptation are planned work. They aren't shipped features of this release.

For now, Ghost knows more routes through your apps, and you get a record you can inspect before sending it through the screen.

[Join the Discord](https://discord.gg/gmvDX4Juk) to share the skills and things you build with Ghost, report failures, and get support. Bring your phone. Help teach the ghost.
