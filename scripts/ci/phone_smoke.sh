#!/usr/bin/env bash
# Run one phone-CI skill test against an already-booted emulator.
#
#   scripts/ci/phone_smoke.sh <skill>            # runs tests/phone/test_<skill>.py
#
# Used by .github/workflows/phone-smoke.yml (inside android-emulator-runner's
# `script:`), and runnable locally against any emulator:
#
#   PHONE_CI_DEVICE=emulator-5554 scripts/ci/phone_smoke.sh tap_smoke
#
#   scripts/ci/phone_smoke.sh --settle-only      # boot + settle, no tests (AVD snapshot step)
#
# Writes pytest JUnit XML + per-test failure captures to $PHONE_CI_ARTIFACTS.
set -euo pipefail

skill="${1:?usage: phone_smoke.sh <skill> | --settle-only}"
settle_only=0
if [[ "$skill" == "--settle-only" ]]; then
  settle_only=1
  skill=snapshot
else
  test_file="tests/phone/test_${skill}.py"
  [[ -f "$test_file" ]] || { echo "::error::no test file $test_file for skill '$skill'"; exit 2; }
fi

export PHONE_CI_DEVICE="${PHONE_CI_DEVICE:-emulator-5554}"
export PHONE_CI_ARTIFACTS="${PHONE_CI_ARTIFACTS:-phone-ci-artifacts}"
mkdir -p "$PHONE_CI_ARTIFACTS"
adb_() { adb -s "$PHONE_CI_DEVICE" "$@"; }

echo "── preparing $PHONE_CI_DEVICE"
booted=0
if timeout 120 adb -s "$PHONE_CI_DEVICE" wait-for-device; then
  for _ in $(seq 1 60); do
    if [[ "$(timeout 10 adb -s "$PHONE_CI_DEVICE" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then booted=1; break; fi
    sleep 2
  done
fi
if [[ $booted -ne 1 ]]; then
  echo "::error::emulator $PHONE_CI_DEVICE never finished booting"
  adb devices -l > "$PHONE_CI_ARTIFACTS/adb-devices-${skill}.txt" 2>&1 || true
  # adb blocks forever on an absent serial, so bound every capture.
  timeout 30 adb -s "$PHONE_CI_DEVICE" logcat -d > "$PHONE_CI_ARTIFACTS/boot-logcat-${skill}.txt" 2>&1 || true
  exit 3
fi
adb_ shell settings put global window_animation_scale 0
adb_ shell settings put global transition_animation_scale 0
adb_ shell settings put global animator_duration_scale 0
adb_ shell settings put system screen_off_timeout 2147483647
adb_ shell svc power stayon true
adb_ shell getprop ro.build.version.release | sed 's/^/android /'
adb_ shell wm size

# A freshly booted image keeps optimizing packages and starting Google services for
# a while; until then a uiautomator dump can take 10+ s, never reach an idle state,
# or find no window at all ("null root node": launcher not up). Wait until two
# consecutive dumps succeed quickly, nudging the device (wake, unlock, HOME) after
# every failed dump so a missing or locked launcher gets brought back.
nudge_home() {
  adb_ shell input keyevent KEYCODE_WAKEUP || true
  adb_ shell wm dismiss-keyguard || true
  adb_ shell input keyevent KEYCODE_HOME || true
}

wait_ui_idle() {  # wait_ui_idle <timeout_s>; returns 1 if the UI never became idle
  local deadline=$((SECONDS + $1)) ok=0 t0 dt out
  nudge_home
  while ((SECONDS < deadline)); do
    t0=$SECONDS
    out=$(timeout 30 adb -s "$PHONE_CI_DEVICE" shell uiautomator dump /sdcard/settle.xml 2>&1 || true)
    dt=$((SECONDS - t0))
    echo "   settle: dump took ${dt}s: ${out:0:45}"
    if [[ "$out" == *"dumped to"* ]] && ((dt <= 6)); then
      ok=$((ok + 1))
      ((ok >= 2)) && { echo "── UI idle"; return 0; }
    else
      ok=0
      nudge_home
    fi
    sleep 2
  done
  return 1
}

echo "── waiting for UI idle"
if ((settle_only)); then
  # Fatal: actions/cache only saves on job success, so failing here keeps an
  # unsettled device out of the cached snapshot.
  if ! wait_ui_idle "${PHONE_CI_SNAPSHOT_SETTLE_TIMEOUT:-90}"; then
    echo "::error::UI never became idle before snapshot; not caching this AVD"
    timeout 30 adb -s "$PHONE_CI_DEVICE" logcat -d > "$PHONE_CI_ARTIFACTS/settle-logcat-snapshot.txt" 2>&1 || true
    exit 4
  fi
  exit 0
fi
if ! wait_ui_idle "${PHONE_CI_SETTLE_TIMEOUT:-120}"; then
  echo "::warning::UI did not become idle within ${PHONE_CI_SETTLE_TIMEOUT:-120}s; running tests anyway"
fi

echo "── running $test_file"
status=0
"${PYTHON:-python3}" -m pytest "$test_file" -v --tb=short -p no:cacheprovider \
  --junitxml="$PHONE_CI_ARTIFACTS/junit-${skill}.xml" || status=$?

if [[ $status -ne 0 ]]; then
  adb_ logcat -d -t 5000 > "$PHONE_CI_ARTIFACTS/logcat-${skill}.txt" 2>&1 || true
  adb_ exec-out screencap -p > "$PHONE_CI_ARTIFACTS/final-screen-${skill}.png" 2>/dev/null || true
fi
exit $status
