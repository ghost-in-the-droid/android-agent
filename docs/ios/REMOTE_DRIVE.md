# Remote-driving a USB iPhone from the Linux Ghost host

**Status:** design draft (ios-tester@mac half). Pairs with core-dev's Ghost-side
config/naming/fleet strawman. Not blocking the F2 / TTS / H.264 / animationCoolOff PRs.

**Topology:** `Linux Ghost host ──SSH──> Mac (Appium+WDA) ──RemoteXPC tunnel──> USB iPhone`

The iPhone-facing leg (RemoteXPC tunnel, codesign, WDA lifecycle) stays **entirely
Mac-local** and unchanged. The new leg is only Ghost→Mac. The core principle below
falls out of that: **the Ghost host talks to Appium/WDA HTTP over a forward; it never
touches the device's IPv6 tunnel directly.**

---

## TL;DR recommendation

- **Transport:** one persistent, multiplexed SSH tunnel per Mac (`ControlMaster` +
  `autossh`/`ControlPersist`), forwarding Appium `:4723`, WDA `:8100`, MJPEG `:9100`,
  H.264 WS `:9200`. Not per-session forwards. LAN SSH overhead is negligible vs WDA's
  own latency (see numbers). WireGuard is the fleet/WAN upgrade, not v1.
- **Failure model:** SSH drop ≠ WDA session death. The Appium/WDA session lives on the
  Mac and survives a transport drop until `newCommandTimeout` (300s). So: supervised
  reconnect + backoff, then **revalidate & reattach** the cached session; re-init only
  if it actually expired. Our session cache + `_validate_session_id` already support this.
- **Security:** never bind WDA/Appium to `0.0.0.0`; expose **only** via SSH forward
  (access == possession of the SSH key). Restricted key (`permitopen`, forced-command,
  no agent-forwarding). Highest-value control is a **Ghost-side confirmation gate for
  destructive/irreversible actions** — the phone is CKL's personal device with real
  accounts. WDA token = optional hardening; SSH cert CA when it's a fleet.
- **Already abstracted (good news):** `wda_url` config field (`IOS_WDA_URL`) +
  configurable Appium host/port mean the WDA client is URL-agnostic today. Remote mode
  is mostly "point it at the forwarded localhost ports + skip the Mac-local tunnel-IPv6
  candidate discovery."

---

## Item 2 — Auth (Linux→Mac SSH hop)

- **SSH key is fine.** No reason for cert-based at v1 (single Mac). My Mac uses standard
  key auth; sshd needs Remote Login enabled + the Ghost's pubkey in `authorized_keys`.
- **Harden the key**, don't just drop it in: dedicated `ed25519` keypair per Ghost host,
  and in `authorized_keys` restrict it —
  `restrict,permitopen="127.0.0.1:4723",permitopen="127.0.0.1:8100",permitopen="127.0.0.1:9100",permitopen="127.0.0.1:9200",command="/usr/bin/false"`
  (pure port-forward key, no shell, no agent/X11 forward, no PTY). If we also want the
  Mac-side report command (below), use a forced-command wrapper instead of `false`.
- **No agent-forwarding** from Ghost onto the Mac (don't expose the Ghost's agent to the
  Mac end).
- **Cert-based (SSH CA):** worth it at **fleet scale** (N Macs) — a short-lived cert
  signed by a Ghost CA beats maintaining `authorized_keys` on every Mac, and gives
  expiry/revocation for free. Recommend: plain key for v1, SSH CA in the fleet phase.

## Item 3 — Transport

**Latency budget (measured this session, WDA-side):** `status` 5ms · `screenshot` 191ms
· `tap` 728ms (post animationCoolOff fix). On a wired/LAN hop, SSH adds **~1–3ms RTT +
negligible crypto** on Apple Silicon. So control latency is WDA-bound, not transport-bound
— **HTTP-over-SSH is good enough for interactive tap.** No need for a lower-overhead RPC.

**Preferred: one persistent multiplexed SSH tunnel per Mac**, not per-session forwards:
- Per-session forwards add setup/teardown churn and complicate reconnection; a single
  supervised tunnel is simpler and keeps sessions warm.
- Multiplex with `ControlMaster auto` + `ControlPersist`; supervise with `autossh` (or a
  small systemd/loop on the Ghost side) + `ServerAliveInterval 15`.
- Forward the four ports: `4723` (Appium control plane), `8100` (WDA — needed for the
  direct `/wda/*` calls like `/wda/speak` that Appium doesn't proxy), `9100` (MJPEG),
  `9200` (H.264 WS).

**H.264 stream over the same tunnel — caveat worth flagging:** the H.264 port (`:9200`)
is **not** Appium-forwarded; on the Mac it's reached via the RemoteXPC tunnel. For remote
use we forward `:9200` over SSH too. That works on LAN, **but** WebSocket-over-SSH is
TCP-over-TCP, which suffers head-of-line blocking under packet loss. On a clean LAN it's
fine (I validated the stream is decent locally). Over WAN/lossy links it degrades — that's
the trigger to move the **stream specifically** (or everything) onto **WireGuard (UDP)**,
which has no TCP-over-TCP pathology and gives a flat network for the fleet. So:
- **v1 / LAN:** everything over the one SSH tunnel, including H.264.
- **WAN or multi-site:** WireGuard underlay; SSH (or plain HTTP) rides on top. The stream
  is 6 Mbps — fine for the tunnel CPU-wise, but latency-sensitive, so it's the first thing
  that wants UDP transport.

## Item 4 — Failure mode when SSH drops mid-session

**Key fact that decides everything: a dropped SSH tunnel does NOT kill the WDA session.**
The Appium process + WDA-on-device live on the Mac; SSH is only transport. The session
survives a transport blip up to Appium's `newCommandTimeout` (we set **300s**). So:

- **Reconnect with exponential backoff** (supervised tunnel), then **revalidate the cached
  WDA session** (`GET /session/:id/status` / our `_validate_session_id`) and **reattach**
  if alive. Re-init only if it genuinely expired. This is effectively checkpoint+resume,
  and `ios.py` already caches session IDs per config + validates on reuse — minimal new code.
- **Keep sessions warm across brief drops:** either bump `newCommandTimeout` for remote
  deployments (e.g. 600s) or have the Ghost side send a periodic no-op keepalive
  (`GET /status`) so a 30–60s reconnect never races the timeout.
- **Two independent failure domains — don't conflate:** (a) the Ghost→Mac **SSH tunnel**
  (this item; supervised on the Ghost side), and (b) the Mac→iPhone **RemoteXPC tunnel**
  (stays Mac-local, already supervised by `ghost-ios`). A Ghost-side reconnect must NOT try
  to fix the device tunnel — it just re-dials SSH and revalidates the session; if the
  device tunnel is the thing that died, the Mac's own supervisor + health surface report it.

## Item 7 — Existing hooks / how much transport is already abstracted

More than you'd hope:
- **`wda_url` config field** (`IOS_WDA_URL` / `IOS_WEBDRIVERAGENT_URL`) is already wired
  into both the session caps (`appium:webDriverAgentUrl`) and `_wda_base_url()` (used by
  direct `/wda/*` calls). The WDA client is **URL-agnostic today** — point it at the
  forwarded port and it works.
- **Appium host/port are config**, not hardcoded — same story for the control plane.
- **`IOS_USE_PREINSTALLED_WDA` / `appium:usePreinstalledWDA`** already expresses "WDA is
  already up, don't spawn it." That's exactly the remote posture: the **Mac owns WDA
  lifecycle**, the Ghost host never builds/signs/spawns WDA. Combined with
  `IOS_USE_PREBUILT_WDA`, the Mac keeps a warm prebuilt WDA and the Ghost just drives it.
- **Session mgmt** (`_sessions` cache keyed by config tuple, `_validate_session_id`,
  per-config lock) supports reattach — good for item 4.
- **The one Mac-local assumption to abstract:** `h264_stream.py::_candidate_urls` discovers
  the device stream via the **RemoteXPC tunnel IPv6** (from the `:42314` registry) — those
  `fdxx::` addresses are only routable **on the Mac**. In remote mode the Ghost host must
  **skip tunnel-IPv6 discovery** and use the forwarded `localhost:9200` directly. Add a
  "remote/forwarded" flag to the candidate logic (or just prefer localhost when the ref is
  `@host`). This is the main transport gap; the rest is config.

## Item 8 — Security surface & threat model

**Today:** WDA (`:8100`), Appium (`:4723`), MJPEG (`:9100`), H.264 WS (`:9200`) are all
**unauthenticated, localhost-only** on the Mac. Fine while localhost-only; becomes the
whole ballgame the moment we tunnel.

**Threat model (Mac end):** the Mac is CKL's personal machine driving a **real personal
iPhone** — live Apple ID, WhatsApp, TikTok, banking apps, photos. The asset is those
accounts/data. Threats, in priority order:
1. **Compromised/confused Ghost host** → full iPhone control. This is the real one. A WDA
   token does *not* stop it (the attacker proxies through the legitimate tunnel). Mitigate
   with a **Ghost-side confirmation gate on destructive/irreversible actions** (app delete,
   purchases, sending messages/DMs, factory-reset gestures) + an action allowlist per remote.
2. **LAN attacker** → mitigated by **localhost-only bind + SSH-only exposure** (never
   `0.0.0.0`). Access requires the SSH key.
3. **Lateral movement on the Mac** (someone already on the Mac's loopback but without the
   SSH key) → optional **WDA shared-secret header token** raises the bar here. Modest value.

**Recommended v1 posture:**
- **Never bind WDA/Appium/stream to `0.0.0.0`.** Localhost-only + SSH forward is the
  primary control.
- **Restricted SSH key** (`permitopen` to the 4 ports, no shell/agent/PTY).
- **Ghost-side destructive-action confirmation gate** — highest ROI, and it's a Ghost-side
  policy layer core-dev likely already has hooks for (mirror it from any existing
  Android destructive-action guard).
- **Optional:** WDA header token (`X-Ghost-Token`) checked by the WDA patch — cheap defense
  in depth; I can add it to the GhostAgent WDA fork the same way I added `/wda/speak`.
- **Fleet:** WireGuard gives mutual auth + encryption at the network layer, and SSH certs
  give key lifecycle. Both are phase-2.

---

## Pushback / +1 on core-dev's Ghost-side strawman (1, 5, 6)

- **(1) Static config over mDNS — agree for v1.** mDNS adds a daemon + LAN-trust question
  for little gain at small N. **But do NOT hand-edit UDIDs into the config.** UDIDs are
  40-char opaque strings (I hit a *phantom* UDID in the brief this session that existed
  nowhere — hand-maintained UDID lists rot and mislead). Instead: config carries the Mac
  **endpoint** (ssh host + ports); **auto-discover attached UDIDs from the Mac.**
- **Answer to your item-6 open question: YES, a tiny Mac-side report agent — and it already
  half-exists.** `ghost-ios status` enumerates attached devices + tunnel/WDA health.
  Add `ghost-ios report --json` emitting `{udid, name, ios_version, wda_up, tunnel_up}`
  per attached phone. The Ghost registers a Mac with **one `remotes:` line**, then a
  `ghost probe mac1` SSHes in, runs `ghost-ios report --json`, and **auto-populates the
  `devices:`** — no hand-typed UDIDs. It's the same SSH hop, no new daemon, no mDNS.
- **(5) `@host` naming — agree, clean.** `iphone-15-pro@mac1`, `is_remote_ref` parses
  `@host`, `list_devices` merges local ADB serials + remote refs. One ask: keep the
  **UDID out of the ref** (map name→UDID on the Mac via the report) so refs stay stable and
  human-readable, and a phone that moves Macs just changes its `@host`.
- **(6) Multi-Mac fleet — agree the config scales**, and the report agent makes
  registration one command instead of UDID archaeology. At fleet scale, layer in SSH certs
  (item 2) + WireGuard (item 3).

## Two constraints I own that shape "what a Mac fleet node is"

1. **GUI-session requirement (F3):** WDA codesign needs an interactive Aqua login session
   (`errSecInternalComponent` from headless/SSH). So a remote Mac node **must auto-login to
   a desktop and stay unlocked** (`caffeinate`, disable screensaver lock, keychain
   auto-lock off). A headless CI Mac won't work unless it auto-logs-in a GUI session. This
   bounds the fleet: iOS nodes are *always-logged-in Macs*, physical or hosted-with-auto-login.
2. **Single WDA owner per device:** one WDA session per iPhone. If a Mac-local process and
   the remote Ghost both drive, they contend. Rule: **the Mac's Appium is the single owner;
   the Ghost always drives through Appium** so it serializes. The exceptions are the direct
   `/wda/speak` and H.264 paths (they bypass Appium) — those need to respect the same
   per-device lock, or be routed through a Mac-side broker if we ever want true multi-tenant.

---

## Rough phasing

- **v1 (single Mac, LAN):** static `remotes:` endpoint config + `ghost-ios report --json`
  auto-discovery; one supervised multiplexed SSH tunnel (4 ports); remote-mode candidate-URL
  flag (skip tunnel-IPv6); reconnect→revalidate→reattach; localhost-only bind + restricted
  key + Ghost-side destructive-action gate.
- **v2 (fleet / WAN):** WireGuard underlay (fixes stream HoL blocking, flat net), SSH cert
  CA, optional WDA header token, `ghost probe` registration command.
