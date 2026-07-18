#!/usr/bin/env bash
#
# doctor.sh — preflight for the iOS device stack. Checks every known failure
# point (device wedge, developer mode, keychain lock, signing identity, prebuilt
# WDA, GhostAgent patch, runtime services, tunnel) and prints the fix for each.
# Fast + read-only. Invoked by `ghost-ios doctor`.
set -uo pipefail

GHOST_IOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ios/lib.sh
. "$GHOST_IOS_DIR/lib.sh"

fails=0; warns=0
GRN="[ ok ]" RED="[FAIL]" YEL="[warn]"
chk(){ printf "  %-6s %-26s %s\n" "$1" "$2" "$3"; }

say "== ghost-ios doctor :: ${DEV_REF} =="
say "Checks every known failure point before you build/run. (fast, read-only)"
say ""

require_udid

# 1. GUI vs SSH — codesign needs a GUI (Aqua) session
if [ -n "${SSH_CONNECTION:-}" ]; then
  chk "$YEL" "session" "SSH — codesign/WDA-build will fail; build WDA at the Mac console"; warns=$((warns+1))
else
  chk "$GRN" "session" "local GUI (codesign OK)"
fi

# 2. device present (via xctrace — reliable; `devicectl info details` can hang
#    indefinitely, so we must NOT gate presence on it) + best-effort details.
if xcrun xctrace list devices 2>/dev/null | awk '/^== Devices ==$/{f=1;next} /^== /{f=0} f' | grep -qF "$IOS_DEVICE_UDID"; then
  if timeout 8 xcrun devicectl device info details --device "$IOS_DEVICE_UDID" >"$LOG_DIR/doctor-dc.txt" 2>&1; then
    ver=$(grep -iE "osVersionNumber" "$LOG_DIR/doctor-dc.txt" | head -1 | awk -F: '{print $2}' | xargs)
    chk "$GRN" "device" "connected (iOS ${ver:-?})"
    grep -qi "developerModeStatus.*enabled" "$LOG_DIR/doctor-dc.txt" \
      && chk "$GRN" "developer mode" "enabled" \
      || chk "$YEL" "developer mode" "not confirmed -> Settings>Privacy>Developer Mode (if WDA won't launch)"
    warns=$((warns + 0))
  else
    chk "$GRN" "device" "connected (devicectl details unavailable — it can hang; non-fatal)"
  fi
else
  chk "$RED" "device" "NOT attached -> plug in via USB + unlock (xcrun xctrace list devices)"; fails=$((fails+1))
fi

# 3. phone unlocked
if timeout 8 xcrun devicectl device info lockState --device "$IOS_DEVICE_UDID" 2>/dev/null | grep -qi "unlockedSinceBoot: true"; then
  chk "$GRN" "phone lock" "unlocked"
else
  chk "$YEL" "phone lock" "may be locked -> unlock the iPhone"; warns=$((warns+1))
fi

# 4. keychain unlocked + no-timeout (codesign readiness)
kinfo=$(security show-keychain-info "$KEYCHAIN" 2>&1)
if printf '%s' "$kinfo" | grep -qi "no-timeout"; then
  chk "$GRN" "keychain" "unlocked, no auto-lock"
elif printf '%s' "$kinfo" | grep -qi "User interaction is not allowed"; then
  chk "$RED" "keychain" "LOCKED -> ghost-ios keychain (or fix-wda-signing.sh)"; fails=$((fails+1))
else
  chk "$YEL" "keychain" "auto-lock enabled -> ghost-ios keychain (prevents mid-build re-lock)"; warns=$((warns+1))
fi

# 5. signing identity present
if [ -n "$IOS_XCODE_SIGNING_ID" ] && security find-identity -v -p codesigning 2>/dev/null | grep -q "$IOS_XCODE_SIGNING_ID"; then
  chk "$GRN" "signing cert" "present (${IOS_XCODE_SIGNING_ID:0:8}...)"
elif security find-identity -v -p codesigning 2>/dev/null | grep -qi "Apple Development"; then
  chk "$YEL" "signing cert" "Apple Development present but IOS_XCODE_SIGNING_ID unset/mismatched"; warns=$((warns+1))
else
  chk "$RED" "signing cert" "MISSING -> add Apple ID in Xcode > Settings > Accounts"; fails=$((fails+1))
fi

# 6. prebuilt WDA .app exists + is signed
app="$IOS_DERIVED_DATA_PATH/Build/Products/Debug-iphoneos/WebDriverAgentRunner-Runner.app"
if [ -d "$app" ] && codesign -dv "$app" >/dev/null 2>&1; then
  chk "$GRN" "prebuilt WDA" "present + signed"
else
  chk "$YEL" "prebuilt WDA" "missing -> $GHOST_IOS_DIR/fix-wda-signing.sh (only if using prebuilt WDA)"; warns=$((warns+1))
fi

# 7. WDA installed on the phone (a live session proves it; else devicectl, slow)
if wda_up; then
  chk "$GRN" "WDA on device" "installed (session live)"
elif timeout 15 xcrun devicectl device info apps --device "$IOS_DEVICE_UDID" --include-all-apps 2>/dev/null | grep -qi "${IOS_UPDATED_WDA_BUNDLE_ID}.xctrunner"; then
  chk "$GRN" "WDA on device" "installed"
else
  chk "$YEL" "WDA on device" "not found (or query slow) -> fix-wda-signing.sh if launch fails"; warns=$((warns+1))
fi

# 8. GhostAgent /wda/speak patch present in the vendored WDA source (drift detection)
src="$WDA_SRC/WebDriverAgentLib/Commands/FBCustomCommands.m"
patch="$GHOST_REPO/patches/FBCustomCommands.ghostagent.m"
if grep -q "handleSpeak" "$src" 2>/dev/null; then
  grep -q "usesApplicationAudioSession = NO" "$src" 2>/dev/null \
    && chk "$GRN" "GhostAgent patch" "/wda/speak + audio fix present" \
    || chk "$YEL" "GhostAgent patch" "/wda/speak present but audio fix missing -> reapply $patch"
else
  chk "$YEL" "GhostAgent patch" "not applied (TTS off) -> cp $patch over the WDA source; rebuild"
fi

# 9. runtime services
appium_up && chk "$GRN" "appium :$APPIUM_PORT" "up" || { chk "$YEL" "appium :$APPIUM_PORT" "down -> ghost-ios up"; warns=$((warns+1)); }
ghost_up  && chk "$GRN" "backend :$GHOST_PORT" "up"  || { chk "$YEL" "backend :$GHOST_PORT" "down -> ghost-ios up"; warns=$((warns+1)); }

# 10. tunnel registry has the device
if curl -s -m5 "$REG" 2>/dev/null | grep -q '"status":"OK"'; then
  chk "$GRN" "tunnel :$TUNNEL_PORT" "registry has device"
else
  chk "$YEL" "tunnel :$TUNNEL_PORT" "no device entry -> ghost-ios up (supervisor auto-recovers)"; warns=$((warns+1))
fi

say ""
if [ "$fails" -gt 0 ]; then say "== $fails blocking issue(s), $warns warning(s) — fix the [FAIL] lines above =="; exit 1
elif [ "$warns" -gt 0 ]; then say "== ready, $warns warning(s) ([warn] are usually fine / auto-recover) =="; exit 0
else say "== all green — build & run should work =="; exit 0; fi
