#!/bin/bash
# Autonomously archive + export a signed .ipa (no human, no prompt).
#
#   METHOD=development ./scripts/export-ipa.sh   # default: installs on registered devices
#   METHOD=ad-hoc      ./scripts/export-ipa.sh   # shareable to registered UDIDs (needs ad-hoc profile)
#   METHOD=app-store   ./scripts/export-ipa.sh   # TestFlight/App Store (needs Distribution cert)
#
# development works today with the Apple Development cert in ghost-signing.keychain-db.
# ad-hoc / app-store need a Distribution cert added to that keychain + the matching
# provisioning profile (Apple Developer portal). Everything else is identical.
set -euo pipefail

IOS="$(cd "$(dirname "$0")/.." && pwd)"
TEAM="${IOS_XCODE_ORG_ID:-WWD665FH95}"
METHOD="${METHOD:-development}"
SIGN_KC="$HOME/Library/Keychains/ghost-signing.keychain-db"
PWFILE="$HOME/.config/ghost/signing-pw"
ARCHIVE="$IOS/build/GhostLLM.xcarchive"
OUT="$IOS/build/ipa"

if [ -f "$PWFILE" ] && [ -f "$SIGN_KC" ]; then
  security unlock-keychain -p "$(cat "$PWFILE")" "$SIGN_KC" 2>/dev/null || true
  security list-keychains -d user -s "$SIGN_KC" "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1 || true
fi

cd "$IOS"
command -v xcodegen >/dev/null 2>&1 && xcodegen generate >/dev/null

echo "== archiving (method=$METHOD) =="
xcodebuild -project GhostLLM.xcodeproj -scheme GhostLLM \
  -sdk iphoneos -configuration Release -allowProvisioningUpdates \
  -archivePath "$ARCHIVE" DEVELOPMENT_TEAM="$TEAM" \
  OTHER_CODE_SIGN_FLAGS="--keychain $SIGN_KC" archive \
  2>&1 | grep -iE 'ARCHIVE SUCCEEDED|BUILD FAILED|error:|errSec' | tail -8

[ -d "$ARCHIVE" ] || { echo "ARCHIVE_FAILED"; exit 1; }

PLIST="$IOS/ExportOptions-$METHOD.plist"
echo "== exporting IPA =="
rm -rf "$OUT"
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$OUT" \
  -exportOptionsPlist "$PLIST" -allowProvisioningUpdates \
  2>&1 | grep -iE 'EXPORT SUCCEEDED|error:|Exported' | tail -8

IPA="$(ls "$OUT"/*.ipa 2>/dev/null | head -1)"
[ -n "$IPA" ] && echo "IPA_OK: $IPA ($(du -h "$IPA" | cut -f1))" || { echo "EXPORT_FAILED"; exit 1; }
