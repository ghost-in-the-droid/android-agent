---
title: "Remote Fleet: Security Model"
description: The threat model behind remote iOS — why localhost-only + SSH-forward, the restricted key, and the destructive-action confirmation gate.
---

Remote-driving a phone is a security-sensitive feature: the phone at the end of the tunnel is often someone's **real, personal device** — live Apple ID, messengers, banking apps, photos. This page explains what the design protects against and why, so you can judge whether the defaults fit your deployment.

## The surfaces involved

On the Mac, four services participate: Appium (`:4723`), WDA (`:8100`), MJPEG (`:9100`), and the H.264 stream (`:9200`). All four are **unauthenticated by design** — their only protection is *who can reach them*. That is fine while they are loopback-only on the Mac; it becomes the whole ballgame the moment you add remote access. Hence the two load-bearing rules:

1. **Never bind any of them to `0.0.0.0`.** They stay on `127.0.0.1`.
2. **The only remote path is an SSH port-forward.** Access is equivalent to possession of the SSH key.

## Threat model

In priority order:

| # | Threat | Mitigation |
|---|---|---|
| 1 | **Compromised or confused Ghost host** — the Linux machine holding the key is tricked (prompt injection, malicious skill) or breached, and now "legitimately" drives the phone | **Ghost-side destructive-action confirmation gate** (below). Note a WDA-side auth token does *not* help here — the attacker proxies through the legitimate tunnel |
| 2 | **LAN attacker** reaching the Mac's automation ports | Loopback-only bind + SSH-only exposure; nothing listens on the network |
| 3 | **Lateral movement on the Mac** — a process already on the Mac's loopback, without the SSH key | Restricted key limits what the *key* can do; an optional WDA shared-secret header raises this bar further (modest value, defense-in-depth) |

The ranking matters: the realistic risk is #1, and it's the one most "add a token" proposals don't address. The gate does.

## The restricted SSH key

The key authorized on the Mac can forward exactly four loopback ports and nothing else — no shell, no PTY, no agent or X11 forwarding, every exec attempt fails:

```text
restrict,permitopen="127.0.0.1:4723",permitopen="127.0.0.1:8100",permitopen="127.0.0.1:9100",permitopen="127.0.0.1:9200",command="/usr/bin/false" ssh-ed25519 AAAA...
```

Use a dedicated `ed25519` keypair per Ghost host, and never forward your SSH agent onto the Mac. If discovery (`ghost-ios report --json`) should run over the same key, swap `/usr/bin/false` for a forced-command wrapper that permits exactly that command.

## The destructive-action confirmation gate

On a **remote** device, a destructive tool call is intercepted *before dispatch* and returns `CONFIRM_REQUIRED` unless the call carries `confirm: true`:

- **Gated tools:** inherently irreversible / high-impact / code-executing ones — `shell`, `launch_intent`, `run_skill` / `run_action` / `run_workflow`, `create_skill`, `force_stop`, `clear_notifications`. Extend the set with `GITD_DESTRUCTIVE_TOOLS_EXTRA="tool_a,tool_b"`.
- **Fail-closed for unknown tools:** a tool name the gate doesn't recognize, targeting a remote device, is treated as destructive if its name reads destructive (`delete`, `uninstall`, `purchase`, `wipe`, `reset`, `transfer`, …). A tool added later is never silently un-gated.
- **Local devices unaffected:** USB Android/iOS behave exactly as before.
- **Kill-switch:** `REMOTE_CONFIRM_REQUIRED=false` disables the gate. Default is on; think twice before turning it off for a phone you care about.

### Honest scope note (v1)

The gate is **tool-name-based**. It catches semantic destructive tools and the control plane, but on iOS many destructive actions are performed through *generic* `tap`/`type` calls — tapping a "Delete", "Buy", or "Send" button has no destructive tool name to match. That is a conscious v1 limitation, not an oversight: the mitigations there are agent judgment and a human watching remote sessions. A perception-based "confirm irreversible UI sequences" check is planned research, not a shipped control. Size your trust accordingly: the gate meaningfully raises the bar; it is not a sandbox.

## Why not just put a token on WDA?

Because of threat #1. A shared-secret header on WDA (or Appium) authenticates *the tunnel*, and the compromised Ghost host *owns* the tunnel. A token only helps against threat #3 (loopback neighbors on the Mac), which is why it's an optional hardening layer, not the primary control. The primary controls are the restricted key (who can reach the ports) and the Ghost-side gate (what a reached port will do).

## Hardening for larger fleets (planned)

- **SSH certificate CA** — short-lived certs signed by a fleet CA instead of `authorized_keys` on every Mac; expiry and revocation for free. Worth it at N Macs, overkill at one.
- **WireGuard underlay** — mutual auth and encryption at the network layer, and (as a bonus) fixes the TCP-over-TCP head-of-line blocking that makes the H.264 stream degrade on lossy WAN links. LAN deployments don't need it.
- **Optional WDA header token** — cheap defense-in-depth against loopback neighbors.

## Operator checklist

- [ ] Appium/WDA/MJPEG/H.264 bound to `127.0.0.1` on the Mac (default — verify nothing re-bound them)
- [ ] Dedicated restricted key per Ghost host; `permitopen` matches exactly the four ports
- [ ] No SSH agent forwarding to the Mac
- [ ] Confirmation gate on (`REMOTE_CONFIRM_REQUIRED` unset or `true`)
- [ ] Humans review what remote agents do on personal devices, especially UI-level actions the gate can't classify
