---
title: "🙋 Human in the Loop"
description: How to run an AI agent with a human in the loop on Android. A Ghost skill pauses for a captcha, a login, an SMS code or a confirmation, a person handles it, and the agent resumes on the same phone.
---

Some steps on a phone should not be automated: a captcha, a login, a code that arrives by SMS or email, or a confirmation before something destructive. Ghost lets a skill pause at exactly that step, hand it to a person, and continue once the person is done. Everything before and after stays automated.

## How to run an AI agent with a human in the loop on Android

1. **Connect a phone** and start Ghost (see [Connect a Phone](/getting-started/connect-phone/)).
2. **Run a skill** from your agent over MCP with `run_skill`, or from the shell with `ghost skill run`.
3. **The skill pauses** at a `checkpoint` or an `ask` step and shows its prompt, for example "Solve the CAPTCHA on the phone, then resume."
4. **A human handles it** on the phone and resumes (or aborts) from the dashboard, or the skill notices by itself that the step is done.
5. **The agent continues** the same run on the same device.

Your agent never has to solve the captcha or see your code. It only waits.

## Demos: four captchas, one human

Each demo is a fresh agent on a real Android phone, given one plain prompt: open the vendor's captcha demo page, fill it out, and call a human once the captcha shows. The human solves it on the phone and replies "solved"; the agent checks the result. Clips are sped up.

### Google reCAPTCHA

<video src="/media/hitl/hitl-recaptcha.mp4" autoplay muted loop playsinline controls preload="metadata" style="width:100%;border-radius:8px" aria-label="Google reCAPTCHA demo: the agent prepares the page and calls a human for the captcha"></video>

The agent fills the form and ticks the checkbox; the human solves the image challenge; the agent submits and reads "Verification Success".

### hCaptcha

<video src="/media/hitl/hitl-hcaptcha.mp4" autoplay muted loop playsinline controls preload="metadata" style="width:100%;border-radius:8px" aria-label="hCaptcha demo: the agent prepares the page and calls a human for the captcha"></video>

The agent fills the form; the human solves the drag puzzle; the agent submits and confirms the success response.

### BotDetect

<video src="/media/hitl/hitl-botdetect.mp4" autoplay muted loop playsinline controls preload="metadata" style="width:100%;border-radius:8px" aria-label="BotDetect demo: the agent prepares the page and calls a human for the captcha"></video>

The agent opens the demo; the human types the distorted characters and taps Validate; the agent confirms "Correct!".

### MTCaptcha

<video src="/media/hitl/hitl-mtcaptcha.mp4" autoplay muted loop playsinline controls preload="metadata" style="width:100%;border-radius:8px" aria-label="MTCaptcha demo: the agent prepares the page and calls a human for the captcha"></video>

The agent fills the email and password with sample values; the human types the captcha text; the agent confirms the form went through.

## Checkpoint: pause until a human is done

A `checkpoint` step pauses the run for a human:

```yaml
- checkpoint:
    reason: captcha          # captcha | sms | email | login | llm_decision | generic
    prompt: "Solve the CAPTCHA on the phone, then resume."
    success: {kind: text_visible, text: "Welcome"}
    timeout_s: 600           # default 600; 0 waits forever
```

- The engine publishes `reason` and `prompt`, then waits.
- The run continues when a human resumes it, or as soon as the `success:` validator passes (for example, the welcome screen appears).
- Resume or abort a waiting run from the dashboard, or with `POST /api/skills/runs/{id}/resume`.
- A timeout raises `CheckpointTimeoutError` and an abort raises `CheckpointAbortedError`. Neither triggers the automatic retry.
- A checkpoint that has no way to be resumed and no `success:` is skipped.

## Ask: get a typed answer mid-run

An `ask` step collects one answer, checks it against a schema, and stores it for later steps:

```yaml
- ask:
    who: human                 # human | parent_agent | sub_agent
    prompt: "Which contact did the user mean?"
    schema: {type: enum, values: [first, second]}   # str | int | enum | json
    store_as: selection
    timeout_s: 0               # 0 waits forever
```

- **`human`**: the question appears on the dashboard, like a checkpoint.
- **`parent_agent`**: the run pauses and `run_skill` returns `status: needs_input` with a `resume_token`. The calling agent answers, or relays the question to you, then calls:

  ```
  run_skill_resume(token="<token>", answer="\"first\"")
  ```

  or from a shell: `ghost skill resume <token> --answer '"first"'`.
- **`sub_agent`**: a bounded Claude Code call answers, with a fallback when none is available.

Answers are validated strictly. An invalid answer is rejected and the token stays usable. Paused state is stored privately under `~/.ghost/runs/`. Traces and signed run records note who answered and how long it took, never screenshots.

## When to use which

| You need | Use |
|---|---|
| A person to do something on the phone (captcha, login, SMS or email code) | `checkpoint` |
| A confirmation before a destructive action | `checkpoint` |
| A typed answer from a person | `ask` with `who: human` |
| A decision from the agent that called the skill | `ask` with `who: parent_agent` |

## Related

- [Creating Skills: checkpoints and asks](/skills/creating-skills/#checkpoints-gates-and-confirmations)
- [Using Skills: answering an ask](/skills/using-skills/#answering-an-ask)
- [MCP Server](/features/mcp-server/)
