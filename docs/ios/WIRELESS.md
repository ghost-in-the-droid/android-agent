# iOS setup — recommended guide (wired bootstrap → wireless)

The recommended way to run the agent stack against a real iPhone: a **one-time
wired bootstrap**, then **fully wireless** control over Tailscale — launch
WebDriverAgent (WDA) over the air, reach it over Tailscale, and drive it from MCP
tools / the `ghost` CLI / a Claude Code TUI with the **cable unplugged**.
Companion to [DEMO_RECORDING.md](DEMO_RECORDING.md) and
[REMOTE_DRIVE.md](REMOTE_DRIVE.md).

## Recommended path at a glance

```
┌── Part 1: WIRED bootstrap (once, ~10 min) ──────────────┐
│  trust pairing · Developer Mode · "Connect via network" │
│  · DevToolsSecurity · build+sign WDA                     │
└─────────────────────────────────────────────────────────┘
                     │  unplug the cable ↓
┌── Part 2: go WIRELESS (Tailscale) ──────────────────────┐
│  Tailscale on both · set IOS_WDA_URL to the 100.x IP     │
└─────────────────────────────────────────────────────────┘
                     │
┌── Part 3: DAILY use ────────────────────────────────────┐
│  ghost-ios up  →  drive over Tailscale, forever          │
└─────────────────────────────────────────────────────────┘
```

## Do you ever need a cable? — Once.

**Exactly one wired connection per new Mac+iPhone pair, then never again.** Apple
requires USB for the *first* pairing — to establish the trust relationship, turn
on Developer Mode, and enable Xcode's "Connect via network". After that bootstrap
the cable goes in a drawer; day-to-day is 100% wireless.

## Why wireless works (the short version)

Three things line up:

1. **Direct-WDA transport** (`IOS_WDA_DIRECT=1`) — `IOSDevice` talks straight to
   WDA over plain HTTP. No Appium, no CoreDevice device-lookup (the part that
   wedges with *"Could not find the expected device"*).
2. **Tailscale, addressed by IP** — WDA is reachable at the iPhone's **stable
   Tailscale IP** (`http://<iphone-tailscale-ip>:8100`). Tailscale self-heals
   idle drops; raw Wi-Fi does not, and the RemoteXPC tunnel IPv6 address changes
   every restart.
3. **WDA launches over Wi-Fi** — `xcodebuild` sees the phone as a network-paired
   device and starts WDA with no USB present.

> ⚠️ **Use the Tailscale IP, not the LAN IP.** Python `requests`/`urllib` over a
> `192.168.x` LAN address throw `EHOSTUNREACH` because Tailscale's `utun`
> interface captures LAN routing. `curl` masks this; everything works over the
> `100.x` Tailscale IP.

---

# Part 1 — Wired bootstrap (through the wire, one time)

### 1.0 Prerequisites (Mac)
- Xcode + Command Line Tools, a valid Apple signing identity.
- Appium + the XCUITest driver (provides the WDA Xcode project source):
  ```sh
  npm i -g appium && appium driver install xcuitest
  ```
- [Tailscale](https://tailscale.com) app (installed now, signed in in Part 2).
- This repo + its venv (`uv venv && uv sync` or equivalent).

### 1.1 Plug in the cable 🔌 and pair
1. Connect the iPhone to the Mac by USB, tap **Trust** on the phone, enter the
   passcode.
2. Confirm the pairing on the Mac: `xcrun devicectl list devices` (or Xcode →
   Window → **Devices and Simulators**) shows the iPhone.

### 1.2 Enable Developer Mode (on the phone)
Settings → Privacy & Security → **Developer Mode** → **On** → restart the phone.
(The option only appears after the phone has been connected to Xcode once.)

### 1.3 Unlock + Auto-Lock = Never
Settings → Display & Brightness → **Auto-Lock → Never**. The DeveloperDiskImage
**won't mount while the phone is locked**, and a locked phone drops automation.

### 1.4 Turn on network debugging
Xcode → Window → **Devices and Simulators** → select the iPhone → tick
**"Connect via network"**. Confirm it shows **connected** and there's **no**
"Developer Disk Image is not mounted" warning.

### 1.5 Allow automation + build/sign WDA
```sh
sudo DevToolsSecurity -enable          # lets automation attach without prompts
scripts/ios/fix-wda-signing.sh         # builds + codesigns WDA once (one pw prompt)
```
`fix-wda-signing.sh` auto-heals "Device is busy" and populates
`~/Library/Developer/Xcode/DerivedData/wda-ghost`.

### 1.6 Sanity check on the wire
```sh
scripts/ios/ghost-ios up
scripts/ios/ghost-ios smoke      # launches WDA, taps, screenshots
```
If `smoke` passes, the device is fully bootstrapped.

---

# Part 2 — Go wireless (Tailscale)

### 2.1 Tailscale on both devices
Install Tailscale on the **Mac** and the **iPhone**, sign both into the **same
tailnet**. Get the iPhone's Tailscale IP (`100.x.y.z`) from the Tailscale app or
`tailscale status`.

### 2.2 Configure the direct-WDA env
Copy `scripts/ios/ghost-ios.env.example` → `ghost-ios.env` and set:
```sh
export IOS_DEVICE_UDID="00008XXX-XXXXXXXXXXXXXXXX"   # xctrace list devices
export IOS_WDA_DIRECT=1
export IOS_WDA_URL="http://100.x.y.z:8100"           # iPhone's tailscale IP
export GITD_ENABLE_IOS=1                              # iOS ships gate-OFF
```

### 2.3 Unplug the cable. Forever. 🎉
```sh
scripts/ios/ghost-ios down && scripts/ios/ghost-ios up   # relaunch WDA over Wi-Fi
scripts/ios/ghost-ios status                             # WDA up + reachable over Tailscale?
```
`ghost-ios up` now launches WDA over Wi-Fi (`xcodebuild` network destination) —
no USB present.

---

# Part 3 — Daily use (wireless)

```sh
scripts/ios/ghost-ios up          # WDA over Wi-Fi + a self-healing supervisor
scripts/ios/ghost-ios status
```

Drive it any way you like — all over Tailscale, no USB:
- **MCP tools** (direct-WDA env active): `screenshot`, `launch_app`,
  `extract_visible_text`, `tap`, …
- **Claude Code TUI hero demo**: `scripts/showcase/record-hero.sh "<task>"`
  (records phone + terminal, composited).

---

## Optional — staying on the wire (USB-only fallback)

If you don't want Tailscale (air-gapped lab, CI on a wired rig), the same
direct-WDA transport works over USB — just point `IOS_WDA_URL` at a
locally-forwarded WDA instead of the Tailscale IP:
```sh
# forward the on-device WDA port to the Mac over USB, then:
export IOS_WDA_DIRECT=1
export IOS_WDA_URL="http://127.0.0.1:8100"
```
Or omit `IOS_WDA_URL` entirely and let `IOSDevice` resolve the WDA base **fresh
per session** from the RemoteXPC registry (`IOS_REMOTEXPC_REGISTRY`, default
`http://127.0.0.1:42314`). Wireless is recommended because the Tailscale IP is
stable across WDA/tunnel restarts; the registry address changes every restart.

---

## Reliability — what's bulletproof, what needs a babysitter

- **Transport: bulletproof.** `GET /status` returns 200 indefinitely with *no*
  keepalive — Tailscale self-heals. The cable is irrelevant.
- **The WDA process: needs a supervisor.** WDA is an `xcodebuild` test-runner
  that can exit (phone locks, process dies). Relaunch is wireless and automatic,
  but keep the **supervisor running + Auto-Lock = Never**. `ghost-ios up` starts
  it; it relaunches WDA over Wi-Fi if it drops.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| WDA `xcodebuild` dies instantly / "enabling automation mode" timeout | DeveloperDiskImage not mounted | Unlock + Auto-Lock=Never + Developer Mode on, **restart phone**; check Xcode → Devices (Part 1.4) |
| Python `EHOSTUNREACH` but `curl` works | Tailscale `utun` captured LAN routing | Use the `100.x` Tailscale IP, not `192.168.x` |
| "Could not find the expected device" | Appium/CoreDevice wedge | You're not on direct-WDA — set `IOS_WDA_DIRECT=1` + `IOS_WDA_URL` |
| WDA won't launch over network | Device not network-paired | Re-tick "Connect via network" in Xcode Devices (needs the one USB connect, Part 1.4) |
| Connection drops after idle | Phone locked / Auto-Lock | Auto-Lock = Never; keep the supervisor running |
| "Device is busy" during WDA build | stale build/codesign lock | `scripts/ios/fix-wda-signing.sh` (auto-heals) |

## Bootstrap needs the cable — driving never does

The single wired step (Part 1) exists only to let Apple pair the device and
enable network debugging. Everything after — launching WDA, screenshots, taps,
full agent runs, demo recordings — happens over Tailscale with the cable in a
drawer.
