#!/usr/bin/env bash
#
# fix-wda-signing.sh — build + sign the (optionally GhostAgent-patched)
# WebDriverAgent and install it onto the iPhone, cleanly.
#
# Why this exists: the WDA build often fails with "Command CodeSign failed"
# because the login keychain re-locked (a locked keychain blocks codesign even
# though the partition-list grant is permanent). This unlocks it, does a clean
# build+sign to a fixed derivedData path, then installs the .app with devicectl
# so nothing hangs hosting WDA (Appium launches it later via usePrebuiltWDA).
#
# Run in YOUR Terminal (a GUI login session), NOT over SSH:
#   scripts/ios/fix-wda-signing.sh
#
# Config is auto-detected or read from env / a config file — see
# ghost-ios.env.example. Requires: one attached iPhone, an Apple Development
# signing identity, and an Apple team id (IOS_XCODE_ORG_ID).
set -uo pipefail

GHOST_IOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ios/lib.sh
. "$GHOST_IOS_DIR/lib.sh"

require_udid
[ -n "$IOS_XCODE_ORG_ID" ] || { say "ERROR: no Apple team id. Set IOS_XCODE_ORG_ID (see ghost-ios.env.example)."; exit 1; }
[ -d "$WDA_SRC" ] || { say "ERROR: WebDriverAgent source not found at $WDA_SRC"; say "       Install the driver: appium driver install xcuitest"; exit 1; }

say "Target device : $IOS_DEVICE_UDID"
say "Team / bundle : $IOS_XCODE_ORG_ID / $IOS_UPDATED_WDA_BUNDLE_ID"
say "DerivedData   : $IOS_DERIVED_DATA_PATH"
say ""

read -rs -p "Mac login password> " PW; echo; echo
say "== 1/4 unlock login keychain + (re)grant codesign access =="
security unlock-keychain -p "$PW" "$KEYCHAIN" || { say "unlock failed — wrong password?"; exit 1; }
security set-key-partition-list -S apple-tool:,apple: -s -k "$PW" "$KEYCHAIN" >/dev/null 2>&1
# One prompt for everything: the login password is also the sudo password, so
# prime sudo now with it (used only if a CoreDevice reset is needed below). If
# they differ (rare), this no-ops and sudo prompts later only if actually used.
sudo -S -v <<<"$PW" 2>/dev/null || true
unset PW
say "keychain status:"; security show-keychain-info "$KEYCHAIN" 2>&1 | sed 's/^/   /'

APP="$IOS_DERIVED_DATA_PATH/Build/Products/Debug-iphoneos/WebDriverAgentRunner-Runner.app"
BLOG="$LOG_DIR/wda-build.log"
build_once(){
  rm -rf "$IOS_DERIVED_DATA_PATH"
  cd "$WDA_SRC"
  xcodebuild build-for-testing \
    -project WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner \
    -destination "id=$IOS_DEVICE_UDID" -derivedDataPath "$IOS_DERIVED_DATA_PATH" -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="$IOS_XCODE_ORG_ID" PRODUCT_BUNDLE_IDENTIFIER="$IOS_UPDATED_WDA_BUNDLE_ID" \
    GCC_TREAT_WARNINGS_AS_ERRORS=0 COMPILER_INDEX_STORE_ENABLE=NO 2>&1 | tee "$BLOG" \
    | grep -iE "CompileC.*FBCustomCommands|CodeSign|BUILD SUCCEEDED|BUILD FAILED|error:|errSec|Device is busy|Timed out waiting" || true
}

say ""
say "== 2/4 clean build + sign WDA (~3-5 min, no run) =="
build_once
# Auto-heal the "Device is busy (Connecting to)" stale-CoreDevice failure: reset
# usbmuxd/remoted and retry ONCE, instead of making you run killall by hand.
if [ ! -d "$APP" ] && grep -qiE "Device is busy|Timed out waiting for all destinations" "$BLOG" 2>/dev/null; then
  say ""
  say "-> 'Device is busy' — stale CoreDevice connection. Auto-resetting + retrying once."
  reset_coredevice
  say "   unlock the iPhone if it's locked; waiting ~8s for it to re-handshake ..."
  sleep 8
  build_once
fi

if [ ! -d "$APP" ]; then
  say ""
  say "BUILD FAILED — no signed .app produced (see errors above)."
  if grep -qiE "Device is busy|Timed out waiting" "$BLOG" 2>/dev/null; then
    say "Still 'Device is busy' after a CoreDevice reset: UNLOCK the iPhone, replug"
    say "USB, make sure nothing else (ghost-ios up / Xcode) is using it, and rerun."
  else
    say "If you saw 'CodeSign failed / errSecInternalComponent', the keychain is"
    say "still locked or you're not in a GUI Terminal session (codesign needs one)."
  fi
  exit 1
fi

say ""
say "== 3/4 install the signed WDA onto the phone (keep it unlocked) =="
xcrun devicectl device install app --device "$IOS_DEVICE_UDID" "$APP" 2>&1 | tail -4

say ""
say "== 4/4 done =="
say "WDA is signed + installed and the keychain is unlocked so Appium can (re)launch"
say "it. Point the backend at it with IOS_USE_PREBUILT_WDA=true and"
say "IOS_DERIVED_DATA_PATH=$IOS_DERIVED_DATA_PATH (ghost-ios sets these for you)."
