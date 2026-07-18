#!/usr/bin/env bash
#
# lib.sh — shared config resolution + detection for the ghost-ios iOS tooling.
#
# Sourced by ghost-ios and fix-wda-signing.sh. Resolves every setting from, in
# order of precedence:
#   1. the environment (IOS_* vars — the same ones the backend reads)
#   2. an optional config file: $GHOST_IOS_ENV, ./ghost-ios.env, or
#      ~/.config/ghost-ios.env  (copy ghost-ios.env.example to start)
#   3. auto-detection (single attached device, signing identity, appium path)
#
# There are NO hardcoded personal identifiers. Zero-config works when exactly one
# iPhone is attached and one "Apple Development" identity is in your keychain;
# otherwise set the few IOS_* vars in a config file once.

# The caller exports GHOST_IOS_DIR (the directory these scripts live in).
: "${GHOST_IOS_DIR:?lib.sh: set GHOST_IOS_DIR before sourcing}"

# --- optional config file (first that exists wins) ---------------------------
for _cfg in "${GHOST_IOS_ENV:-}" "$GHOST_IOS_DIR/ghost-ios.env" "$HOME/.config/ghost-ios.env"; do
  [ -n "$_cfg" ] && [ -f "$_cfg" ] && { # shellcheck disable=SC1090
    . "$_cfg"; break; }
done

# --- repo root (two levels above scripts/ios/, overridable) ------------------
GHOST_REPO="${GHOST_REPO:-$(cd "$GHOST_IOS_DIR/../.." 2>/dev/null && pwd)}"

# --- detection helpers (only run when the corresponding var is unset) ---------
detect_udid(){
  # Exactly-one attached physical iOS device via xctrace (~1.7s, reliable —
  # `devicectl device info details` can hang). Prints nothing if 0 or >1 so the
  # user is told to set IOS_DEVICE_UDID explicitly. Simulators (UUIDs with 4
  # dashes) and the Mac host line are excluded.
  local sect ids
  # ONLY the online "== Devices ==" section — stop at the next "== ..." header so
  # "== Devices Offline ==" (e.g. an unplugged iPad) and "== Simulators ==" are
  # excluded. Drop the Mac host line (its id is a 4-dash UUID anyway).
  sect="$(timeout 12 xcrun xctrace list devices 2>/dev/null | awk '/^== Devices ==$/{f=1;next} /^== /{f=0} f')"
  ids="$(printf '%s\n' "$sect" | grep -iv 'Mac' \
        | grep -oE '[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}|[0-9A-Fa-f]{40}' | sort -u)"
  [ "$(printf '%s' "$ids" | grep -c .)" = "1" ] && printf '%s' "$ids"
}

detect_signing_id(){
  # SHA-1 of the "Apple Development" codesigning identity in the login keychain.
  security find-identity -v -p codesigning 2>/dev/null \
    | grep -i 'Apple Development' | head -1 | grep -oE '[0-9A-F]{40}' | head -1
}

detect_team(){
  # Apple team id = OU of the Apple Development cert. Best-effort.
  security find-certificate -a -c 'Apple Development' -p 2>/dev/null \
    | openssl x509 -noout -subject -nameopt multiline 2>/dev/null \
    | awk -F'= ' '/organizationalUnitName/{print $2; exit}'
}

detect_appium(){
  command -v appium 2>/dev/null && return 0
  local p
  for p in "$HOME/.npm-global/bin/appium" /opt/homebrew/bin/appium /usr/local/bin/appium; do
    [ -x "$p" ] && { printf '%s\n' "$p"; return 0; }
  done
}

# --- resolved config (env/file win; detection fills the gaps) ----------------
IOS_DEVICE_UDID="${IOS_DEVICE_UDID:-$(detect_udid)}"
IOS_XCODE_SIGNING_ID="${IOS_XCODE_SIGNING_ID:-$(detect_signing_id)}"
IOS_XCODE_ORG_ID="${IOS_XCODE_ORG_ID:-$(detect_team)}"
IOS_UPDATED_WDA_BUNDLE_ID="${IOS_UPDATED_WDA_BUNDLE_ID:-com.example.WebDriverAgentRunner}"
IOS_DERIVED_DATA_PATH="${IOS_DERIVED_DATA_PATH:-$HOME/Library/Developer/Xcode/DerivedData/wda-ghost}"
APPIUM_BIN="${APPIUM_BIN:-$(detect_appium)}"
KEYCHAIN="${KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"

# ports (overridable)
APPIUM_PORT="${APPIUM_PORT:-4723}"
GHOST_PORT="${GHOST_PORT:-5055}"
TUNNEL_PORT="${TUNNEL_PORT:-42314}"
VITE_PORT="${VITE_PORT:-6175}"
WDA_PORT="${WDA_PORT:-8100}"

# derived
DEV_REF="ios:${IOS_DEVICE_UDID}"
REG="http://127.0.0.1:${TUNNEL_PORT}/remotexpc/tunnels/${IOS_DEVICE_UDID}"
LOG_DIR="${GHOST_IOS_LOG_DIR:-/tmp/ghost-ios}"; mkdir -p "$LOG_DIR"
WDA_SRC="$HOME/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent"
if [ -x "$GHOST_REPO/.venv/bin/python" ]; then PYBIN="$GHOST_REPO/.venv/bin/python"; else PYBIN="python3"; fi

# --- small shared utilities --------------------------------------------------
say(){ printf '%s\n' "$*"; }
ts(){ date '+%H:%M:%S'; }

# --- health probes (shared by ghost-ios + doctor.sh) -------------------------
appium_up(){ curl -sf -m3 "http://127.0.0.1:${APPIUM_PORT}/status" >/dev/null 2>&1; }
ghost_up(){  curl -sf -m8 "http://127.0.0.1:${GHOST_PORT}/api/health" >/dev/null 2>&1; }
vite_up(){   curl -sf -m3 "http://localhost:${VITE_PORT}/" >/dev/null 2>&1; }  # vite binds IPv6 ::1
tunnel_up(){ curl -s -m5 "$REG" 2>/dev/null | grep -q '"status":"OK"'; }
wda_up(){    curl -sf -m3 "http://127.0.0.1:${WDA_PORT}/status" >/dev/null 2>&1; }

require_udid(){
  [ -n "$IOS_DEVICE_UDID" ] && return 0
  say "ERROR: no iOS device UDID. Attach exactly one iPhone (USB, unlocked) so it"
  say "       can be auto-detected, or set IOS_DEVICE_UDID (see ghost-ios.env.example)."
  say "       Attached devices:"; xcrun xctrace list devices 2>/dev/null | sed -n '/== Devices ==/,/== Simulators ==/p' | sed 's/^/         /'
  exit 1
}

reset_coredevice(){
  # Clear a stale CoreDevice/usbmux connection — the cause of xcodebuild's
  # "Device is busy (Connecting to ...)" / "Timed out waiting for all
  # destinations". Bounces the whole device-connection stack (usbmux + remoted
  # + CoreDeviceService); all auto-restart via launchd. Briefly drops USB
  # devices. Needs sudo (caller should `sudo -v` first for a seamless prompt).
  say "[reset ] bouncing usbmuxd + remoted + CoreDeviceService (they auto-restart) ..."
  sudo killall -9 usbmuxd remoted 2>/dev/null || true
  sudo pkill -9 -f CoreDeviceService 2>/dev/null || true
}

export_backend_env(){
  # Hand the backend the same iOS knobs the tuned setup uses. Only non-empty
  # identity vars are exported so an unset value falls through to app defaults.
  local v
  for v in IOS_DEVICE_UDID IOS_XCODE_ORG_ID IOS_UPDATED_WDA_BUNDLE_ID IOS_XCODE_SIGNING_ID IOS_DERIVED_DATA_PATH; do
    [ -n "${!v:-}" ] && export "${v?}"
  done
  export IOS_USE_PREBUILT_WDA="${IOS_USE_PREBUILT_WDA:-true}"
  # MJPEG stream tuning: half-res + 25fps + q65 → far smoother than full-res Retina.
  export IOS_MJPEG_SCALING_FACTOR="${IOS_MJPEG_SCALING_FACTOR:-50}"
  export IOS_MJPEG_SERVER_FRAMERATE="${IOS_MJPEG_SERVER_FRAMERATE:-25}"
  export IOS_MJPEG_SERVER_SCREENSHOT_QUALITY="${IOS_MJPEG_SERVER_SCREENSHOT_QUALITY:-65}"
}
