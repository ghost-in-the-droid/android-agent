---
title: "Remote Fleet: Mac Setup"
description: Prepare a Mac as an iOS fleet node — auto-login GUI session, restricted SSH key, keychain auto-unlock, and the ghost-ios tooling.
---

The Mac in a remote fleet is a worker node: it owns the WebDriverAgent lifecycle, the RemoteXPC device tunnel, and code-signing. The Linux Ghost host only ever reaches it through an SSH port-forward. This page turns a stock Mac into that node.

## 1. The GUI-session requirement (read this first)

WDA code-signing fails with `errSecInternalComponent` from a headless context. A fleet Mac **must auto-login to a desktop (Aqua) session and stay unlocked**:

- **Auto-login:** System Settings → Users & Groups → Automatically log in as the automation user. (FileVault must be off for true unattended reboot-to-desktop.)
- **Never sleep:** System Settings → Lock Screen → never require password after screensaver; Energy → prevent sleeping. Belt-and-suspenders: run `caffeinate -dis` as a login item or LaunchAgent.
- **Keychain stays unlocked:** the login keychain unlocks with auto-login, but disable auto-lock so long-running signing works:

  ```bash
  security set-keychain-settings login.keychain   # no -l/-u/-t flags = never auto-lock
  ```

A headless CI Mac won't work unless it auto-logs into a GUI session. This bounds what an iOS fleet node can be: an always-logged-in Mac, physical or hosted-with-auto-login.

## 2. Enable SSH, add a restricted key

Enable Remote Login (System Settings → General → Sharing → Remote Login), then authorize the Ghost host's key — **restricted**, not a plain key line. Generate a dedicated `ed25519` keypair per Ghost host, and in `~/.ssh/authorized_keys` on the Mac:

```text
restrict,permitopen="127.0.0.1:4723",permitopen="127.0.0.1:8100",permitopen="127.0.0.1:9100",permitopen="127.0.0.1:9200",command="/usr/bin/false" ssh-ed25519 AAAA...ghost-host-key
```

What this buys you:

- `restrict` — no PTY, no agent forwarding, no X11: the key can't get a shell.
- `permitopen` ×4 — the key can forward **only** the four automation ports (Appium, WDA, MJPEG, H.264), all on loopback.
- `command="/usr/bin/false"` — any exec attempt dies immediately. If you also want the Ghost host to run `ghost-ios report --json` over SSH (device discovery), replace `/usr/bin/false` with a forced-command wrapper that allows exactly that command.

Never forward your SSH agent from the Ghost host to the Mac.

## 3. Install the Ghost iOS tooling

On the Mac, install Ghost plus the iOS host tools:

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd android-agent
pip install -e .
npm install -g appium && appium driver install xcuitest
```

Then follow the standard [WebDriverAgent setup](/ios/setup/wda/) once at the Mac's console (the signing step needs the GUI). Set the node up for warm sessions:

```bash
export IOS_USE_PREBUILT_WDA="true"
export IOS_USE_PREINSTALLED_WDA="true"
```

The Mac owns WDA end-to-end. The remote Ghost host never builds, signs, or spawns WDA — it just drives sessions through the forwarded ports.

Day-to-day the node runs under the `ghost-ios` toolkit: `ghost-ios keychain` once (grants CLI codesign access), then `ghost-ios up` starts the backend, Appium, and a self-healing RemoteXPC tunnel supervisor. Note the toolkit is still being packaged into the repository — see [Utility Scripts](/ios/util-scripts/) for its status and full command reference.

## 4. Keep everything loopback-only

Appium, WDA, MJPEG, and the H.264 stream must stay bound to `127.0.0.1` on the Mac — the defaults. **Never bind them to `0.0.0.0`.** Exposure happens exclusively through the SSH forward, so access requires possession of the restricted key. This is the primary security control; see [Security](/ios/remote-fleet/security/).

## 5. Health surface

`ghost-ios status` enumerates attached devices plus tunnel/WDA health on the node, and `ghost-ios report --json` emits a machine-readable inventory the Linux side uses for discovery:

```json
{
  "schema": 1,
  "host": "my-mac",
  "generated_at": "2026-07-11T21:33Z",
  "devices": [
    {
      "udid": "00008XXX-XXXXXXXXXXXXXXXX",
      "name": "my iPhone",
      "ref_slug": "my-iphone",
      "ios_version": "26.4",
      "wda_up": false,
      "appium_up": true,
      "tunnel_up": true
    }
  ]
}
```

Notes on reading it honestly:

- `ref_slug` derives from the phone's user-assigned device name — that's what you use in `<name>@<host>` refs. Two phones of the same model stay distinct.
- `wda_up` means "a WDA session is live *right now*". Idle devices report `false`; that is normal. Readiness for a new session is `tunnel_up && appium_up`.
- Identity comes from `xctrace list devices` and is cached — a slow Xcode toolchain still yields a full record.

See [Utility Scripts](/ios/util-scripts/) for the full `ghost-ios` command reference.

## Recovery expectations

The Mac node self-heals the device leg: the RemoteXPC tunnel supervisor auto-reconnects, and stale WDA sessions are reset by the health/fix surface. If the device tunnel dies, the **Mac's** supervisor reports and repairs it — a reconnecting Linux client should never try to fix the device tunnel from afar (it can't; those tunnel IPv6 addresses aren't routable off the Mac).
