# Wireless iOS control — no cable, over Tailscale

Drive a real iPhone from the agent stack **fully wirelessly**: launch
WebDriverAgent (WDA) over the air, reach it over Tailscale, and run MCP tools /
the `ghost` CLI / a Claude Code TUI against it — **with the USB cable
unplugged**. Companion to [DEMO_RECORDING.md](DEMO_RECORDING.md) and
[REMOTE_DRIVE.md](REMOTE_DRIVE.md).

## Do you ever need a cable? — Once.

**Exactly one wired connection per new Mac+iPhone pair, then never again.**
Apple requires USB for the *first* pairing — to establish the trust
relationship, turn on Developer Mode, and enable Xcode's "Connect via network".
After that bootstrap the cable is done forever on that pair; day-to-day is 100%
wireless.

## Why it works (the short version)

Three things line up:

1. **Direct-WDA transport** (`IOS_WDA_DIRECT=1`) — `IOSDevice` talks straight to
   WDA over plain HTTP. No Appium, no CoreDevice device-lookup (the part that
   wedges with *"Could not find the expected device"*).
2. **Tailscale, addressed by IP** — WDA is reachable at the iPhone's **stable
   Tailscale IP** (`http://<iphone-tailscale-ip>:8100`). Tailscale self-heals
   idle drops; raw Wi-Fi does not, and the RemoteXPC tunnel IPv6 address changes
   every restart.
3. **WDA launches over Wi-Fi** — `xcodebuild` sees the phone as a
   network-paired device and starts WDA with no USB present.

> ⚠️ **Use the Tailscale IP, not the LAN IP.** Python `requests`/`urllib` over a
> `192.168.x` LAN address throw `EHOSTUNREACH` because Tailscale's `utun`
> interface captures LAN routing. `curl` masks this; everything works over the
> `100.x` Tailscale IP.

## First-time setup (clean Mac + new iPhone)

### 0. Prerequisites (Mac)
- Xcode + Command Line Tools, a valid Apple signing identity.
- Appium + the XCUITest driver (provides the WDA Xcode project source):
  `npm i -g appium && appium driver install xcuitest`
- [Tailscale](https://tailscale.com) app.
- This repo + its venv (`uv venv && uv sync` or equivalent).

### 1. The one cable connection 🔌
Plug the iPhone into the Mac and:
1. **Trust** the computer on the iPhone prompt.
2. **Developer Mode**: Settings → Privacy & Security → Developer Mode → **On**,
   then restart the phone.
3. **Unlock + Auto-Lock = Never** (Settings → Display & Brightness →
   Auto-Lock). The DeveloperDiskImage **won't mount while the phone is locked**,
   and a locked phone drops automation.
4. **Xcode → Window → Devices and Simulators** → select the iPhone → tick
   **"Connect via network"**. Confirm it shows connected + the DDI is mounted
   (no "Developer Disk Image is not mounted" warning).
5. Allow automation: `sudo DevToolsSecurity -enable`.
6. **Build + sign WDA once** so it's installed and codesigned on the device:
   `scripts/ios/fix-wda-signing.sh` (auto-heals "Device is busy", one password
   prompt), which populates `~/Library/Developer/Xcode/DerivedData/wda-ghost`.

### 2. Tailscale (both devices)
Install Tailscale on the Mac **and** the iPhone, sign both into the **same
tailnet**. Note the iPhone's Tailscale IP (`100.x.y.z`) from the Tailscale app or
`tailscale status`.

### 3. Configure
Copy `scripts/ios/ghost-ios.env.example` → `ghost-ios.env` and set:
```sh
export IOS_DEVICE_UDID="00008XXX-XXXXXXXXXXXXXXXX"   # xctrace list devices
export IOS_WDA_DIRECT=1
export IOS_WDA_URL="http://100.x.y.z:8100"           # iPhone's tailscale IP
export GITD_ENABLE_IOS=1                              # iOS ships gate-OFF
```

### 4. Unplug the cable. Forever. 🎉

## Daily use (wireless)

```sh
scripts/ios/ghost-ios up          # launches WDA over Wi-Fi + a supervisor
scripts/ios/ghost-ios status      # WDA up? reachable over Tailscale?
```

Then drive it any way you like — all over Tailscale, no USB:
- **MCP tools** (with the direct-WDA env): `screenshot`, `launch_app`,
  `extract_visible_text`, `tap`, …
- **Claude Code TUI hero**: `scripts/showcase/record-hero.sh "<task>"`.

## Reliability — what's bulletproof, what needs a babysitter

- **Transport: bulletproof.** `GET /status` returns 200 indefinitely with *no*
  keepalive — Tailscale self-heals. The cable is irrelevant.
- **The WDA process: needs a supervisor.** WDA is an `xcodebuild`
  test-runner that can exit (phone locks, process dies). Relaunch is wireless
  and automatic, but keep the **supervisor running + Auto-Lock = Never**.
  `ghost-ios up` starts the supervisor; it relaunches WDA over Wi-Fi if it drops.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| WDA `xcodebuild` dies instantly / "enabling automation mode" timeout | DeveloperDiskImage not mounted | Unlock + Auto-Lock=Never + Developer Mode on, **restart phone**; check Xcode → Devices |
| Python `EHOSTUNREACH` but `curl` works | Tailscale `utun` captured LAN routing | Use the `100.x` Tailscale IP, not `192.168.x` |
| "Could not find the expected device" | Appium/CoreDevice wedge | You're not on direct-WDA — set `IOS_WDA_DIRECT=1` + `IOS_WDA_URL` |
| WDA won't launch over network | Device not network-paired | Re-tick "Connect via network" in Xcode Devices (needs the one USB connect) |
| Connection drops after idle | Phone locked / Auto-Lock | Auto-Lock = Never; keep the supervisor running |

## Bootstrap needs the cable — driving never does

The single wired step exists only to let Apple pair the device and enable network
debugging. Everything after — launching WDA, screenshots, taps, full agent runs,
demo recordings — happens over Tailscale with the cable in a drawer.
