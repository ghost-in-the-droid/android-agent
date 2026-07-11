---
title: "Remote Fleet: Linux Setup"
description: Point a Linux Ghost host at a remote Mac — remotes config, the supervised SSH tunnel, device refs, and probing.
---

:::caution[Experimental — not yet for real personal devices]
Remote drive is an advanced feature rolling out in slices. The configuration below is built, but the Linux→Mac path becomes **real-device-ready only once the security hardening lands** (see the [rollout status](/ios/remote-fleet/#rollout-status)). Until then, use it with test devices only — not a phone with real accounts. Local on-Mac iOS automation is unaffected and works today.
:::

With the [Mac side](/ios/remote-fleet/mac-setup/) prepared, the Linux Ghost host needs three things: a remotes-config entry describing the Mac, a persistent SSH tunnel forwarding four ports, and a device ref that names the phone.

## 1. Configure the remote

A remote Mac is one JSON entry. Ghost reads it from `GITD_REMOTES_JSON` (a JSON blob), `GITD_REMOTES_FILE` (a path), or a `remotes` key inside your existing `IOS_DEVICES_JSON` / `IOS_CONFIG_FILE` — one config file can describe the whole fleet.

```bash
export GITD_REMOTES_JSON='{
  "my-mac": {
    "ssh": "automation@my-mac.local",
    "appium_port": 4723,
    "wda_port": 8100,
    "mjpeg_port": 9100,
    "h264_port": 9200
  }
}'
```

The ports are **local, Linux-side forwarded ports** — where the tunnel delivers each Mac service. With one Mac the defaults are fine; with several Macs give each its own port range so they never collide:

```json
{
  "my-mac":     { "ssh": "automation@my-mac.local" },
  "studio-mac": { "ssh": "automation@studio-mac.local",
                  "appium_port": 14723, "wda_port": 18100,
                  "mjpeg_port": 19100, "h264_port": 19200 }
}
```

Remote names — the keys of the remotes map, `my-mac` above — are simple identifiers (they appear after the `@` in device refs, so they can't contain `@`). Malformed entries are skipped rather than crashing device listing — check your JSON if a remote silently doesn't appear.

## 2. Open the tunnel

One persistent, multiplexed tunnel per Mac, forwarding the four service ports to the local ports you configured. In `~/.ssh/config` on the Ghost host:

```text
Host my-mac
  HostName my-mac.local
  User automation
  IdentityFile ~/.ssh/ghost_fleet_ed25519
  ControlMaster auto
  ControlPath ~/.ssh/cm-%r@%h:%p
  ControlPersist yes
  ServerAliveInterval 15
  ExitOnForwardFailure yes
  LocalForward 4723 127.0.0.1:4723
  LocalForward 8100 127.0.0.1:8100
  LocalForward 9100 127.0.0.1:9100
  LocalForward 9200 127.0.0.1:9200
```

Supervise it so it survives blips — `autossh` is the simplest option:

```bash
autossh -M 0 -N my-mac
```

(or an equivalent systemd unit / restart loop). Key properties of this design:

- **One warm tunnel, not per-session forwards** — no setup/teardown churn, simpler reconnection.
- **A dropped tunnel does not kill your automation session.** The Appium/WDA session lives on the Mac and survives until `newCommandTimeout`. Ghost reconnects, revalidates its cached session ID, and reattaches; it re-creates the session only if it truly expired. For links that blip longer, raise `newCommandTimeout` (e.g. 600 s) or keep a periodic `GET /status` keepalive so a 30–60 s reconnect never races the timeout.
- **Two failure domains, fixed from two places.** Ghost→Mac SSH is supervised on the Linux side (this page). Mac→iPhone RemoteXPC is supervised on the Mac and is *not* something a Linux reconnect should touch — if the device leg died, the Mac's health surface reports it.

## 3. Address the phone

A remote iPhone is `<name>@<host>` — no `ios:` prefix, no UDID:

```text
my-iphone@my-mac
```

- `<host>` must match a remote name from your remotes config; an `@` ref whose host is unknown is *not* treated as remote (so it can never mis-route), and Android serials never contain `@`, so the grammar is unambiguous.
- `<name>` is the phone's `ref_slug` from `ghost-ios report` — derived from the device's user-assigned name. The UDID is resolved on the Mac; **never hand-maintain UDID lists** (they rot). A phone that moves to another Mac keeps its name and just changes its `@host`.

Remote refs route to the iOS backend automatically and use the standard `IOS_WDA_URL`-style plumbing pointed at your forwarded ports.

Use it anywhere a device ref is accepted:

```text
launch_app("my-iphone@my-mac", "com.google.chrome.ios")
screenshot("my-iphone@my-mac")
```

## 4. Discover devices from the Mac

Rather than hand-typing device details, ask the Mac what's attached (requires the discovery command to be allowed by the [forced-command wrapper](/ios/remote-fleet/mac-setup/#2-enable-ssh-add-a-restricted-key) on the Mac's restricted key):

```bash
ssh my-mac ghost-ios report --json
```

> The `ghost-ios` toolkit is being packaged into the repository — see [Utility Scripts](/ios/util-scripts/) for its status and full command reference.

The JSON inventory (schema in [Mac Setup](/ios/remote-fleet/mac-setup/#5-health-surface)) gives you each phone's `ref_slug`, iOS version, and per-leg health: `tunnel_up`, `appium_up`, `wda_up`. Remember `wda_up: false` on an idle phone is normal — readiness is `tunnel_up && appium_up`.

> `ghost probe <host>` — a one-command wrapper that runs the report and auto-populates device entries — is landing as part of discovery (slice 2). Until then, the SSH one-liner above is the way.

## 5. Confirmation gate for destructive actions

On a remote device, destructive tool calls (shell-level ops, app force-stop, code-executing skill tools, …) return `CONFIRM_REQUIRED` instead of executing, unless the call carries `confirm: true`. Local Android/USB devices are unaffected. This is deliberate: remote phones are often real, personal devices. Details, scope, and the kill-switch are in [Security](/ios/remote-fleet/security/).

## Design record

The full design discussion behind these choices (latency budgets, failure-model analysis, transport trade-offs) lives in the repo: `docs/ios/remote-fleet/` — the Mac-side and Ghost-side design docs pair up and cross-reference this guide.
