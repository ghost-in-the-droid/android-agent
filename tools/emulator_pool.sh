#!/usr/bin/env bash
# Idempotent bootstrap for the headless Android emulator pool on the emulator host.
#
# Run from any machine that can `ssh $GHOST_EMU_HOST` (it re-executes itself remotely),
# or directly on the emulator host with --local. Every step checks before it acts, so
# re-running is safe and only starts what is missing.
#
#   tools/emulator_pool.sh            # bootstrap + start pool on the emulator host
#   tools/emulator_pool.sh status     # show adb devices + load
#   tools/emulator_pool.sh stop       # kill emulators (adb server stays)
#   tools/emulator_pool.sh client     # HERE: install Ghost Portal + tunnel its ports
#
# Then on the client:  export ADB_SERVER_SOCKET=tcp:$GHOST_EMU_HOST:5037 ; adb devices
#
# Image: x86_64 API 34 google_apis (no Play Store, never signed in).
set -euo pipefail

HOST="${GHOST_EMU_HOST:?set GHOST_EMU_HOST to the ssh alias of the emulator host}"
POOL_SIZE="${POOL_SIZE:-2}"
API="${API:-34}"
IMG="system-images;android-${API};google_apis;x86_64"
SDK="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
CMDLINE_ZIP_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
ADB_PORT=5037
MAX_LOAD=8

# Client side (runs HERE, not on the emulator host): install Ghost Portal on every pool emulator,
# enable its accessibility service, and tunnel each emulator's Portal port so the
# engine's fast a11y path works through the remote adb server. uiautomator alone
# fails with "could not get idle state" on animating screens.
if [[ "${1:-}" == "client" ]]; then
  export ADB_SERVER_SOCKET="tcp:$HOST:5037"
  APK="${GHOST_PORTAL_APK:-$(cd "$(dirname "$0")/.." && pwd)/portal/app/build/outputs/apk/debug/app-debug.apk}"
  [[ -f "$APK" ]] || { echo "Portal APK not found: $APK (build portal/ or set GHOST_PORTAL_APK)"; exit 2; }
  tunnels=()
  for s in $(adb devices | awk '/^emulator-/{print $1}'); do
    adb -s "$s" shell pm path com.ghostinthedroid.portal >/dev/null 2>&1 || adb -s "$s" install -r -g "$APK" >/dev/null
    adb -s "$s" shell 'settings put secure enabled_accessibility_services com.ghostinthedroid.portal/.GhostAccessibilityService; settings put secure accessibility_enabled 1'
    port=$(python3 -c "import sys; sys.path.insert(0, '$(dirname "$0")/..'); from gitd.bots.common.adb import _stable_port; print(_stable_port('$s', 18000))")
    adb -s "$s" forward "tcp:$port" tcp:8080 >/dev/null
    curl -s -m2 "localhost:$port/status" >/dev/null || tunnels+=(-L "$port:127.0.0.1:$port")
    echo "$s portal port $port"
  done
  if ((${#tunnels[@]})); then ssh -f -N -o ExitOnForwardFailure=yes "${tunnels[@]}" "$HOST"; fi
  exit 0
fi

if [[ "${1:-}" != "--local" ]]; then
  exec ssh -o BatchMode=yes "$HOST" "POOL_SIZE=$POOL_SIZE API=$API bash -s -- --local ${1:-up}" < "$0"
fi
shift
CMD="${1:-up}"

export ANDROID_SDK_ROOT="$SDK" ANDROID_HOME="$SDK" ANDROID_AVD_HOME="$HOME/.android/avd"
export PATH="$SDK/cmdline-tools/latest/bin:$SDK/platform-tools:$SDK/emulator:$PATH"
LOGDIR="$HOME/.cache/ghost-emulator-pool"; mkdir -p "$LOGDIR"
log() { printf '[pool %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

load1() { cut -d' ' -f1 /proc/loadavg; }
guard_load() {
  local l; l=$(load1)
  if awk -v l="$l" -v m="$MAX_LOAD" 'BEGIN{exit !(l>m)}'; then
    log "1-min load $l > $MAX_LOAD: shared box busy, refusing to start heavy work"; exit 3
  fi
}

install_sdk() {
  if [[ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]]; then
    log "installing commandline-tools into $SDK"
    mkdir -p "$SDK/cmdline-tools"; tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/clt.zip" "$CMDLINE_ZIP_URL"
    unzip -q "$tmp/clt.zip" -d "$tmp"
    rm -rf "$SDK/cmdline-tools/latest"; mv "$tmp/cmdline-tools" "$SDK/cmdline-tools/latest"
    rm -rf "$tmp"
  fi
  local need=()
  [[ -x "$SDK/platform-tools/adb" ]] || need+=("platform-tools")
  [[ -x "$SDK/emulator/emulator" ]] || need+=("emulator")
  [[ -d "$SDK/system-images/android-${API}/google_apis/x86_64" ]] || need+=("$IMG")
  if ((${#need[@]})); then
    log "sdkmanager install: ${need[*]}"
    yes | sdkmanager --licenses >/dev/null 2>&1 || true
    sdkmanager --install "${need[@]}" >"$LOGDIR/sdkmanager.log" 2>&1
  fi
}

create_avds() {
  for i in $(seq 1 "$POOL_SIZE"); do
    local name="ghost_seed_$i"
    if [[ -f "$ANDROID_AVD_HOME/$name.avd/config.ini" ]]; then continue; fi
    log "creating AVD $name"
    echo no | avdmanager create avd -n "$name" -k "$IMG" -d pixel_6 --force >/dev/null
    local cfg="$ANDROID_AVD_HOME/$name.avd/config.ini"
    # 1080x2400 @ 420dpi, 4 GB RAM, 4 cores, 8 GB data, hardware keyboard off
    for kv in hw.lcd.width=1080 hw.lcd.height=2400 hw.lcd.density=420 \
              hw.ramSize=4096 hw.cpu.ncore=4 disk.dataPartition.size=8G \
              hw.keyboard=yes hw.gpu.enabled=yes hw.gpu.mode=swiftshader_indirect; do
      k=${kv%%=*}; sed -i "/^$k[ =]/d" "$cfg"; echo "$kv" >>"$cfg"
    done
  done
}

start_adb_server() {
  if ss -ltn "sport = :$ADB_PORT" | grep -q "0.0.0.0:$ADB_PORT\|\*:$ADB_PORT"; then return; fi
  # A localhost-only server (from a plain `adb devices`) blocks the port; replace it.
  adb kill-server >/dev/null 2>&1 || true
  log "starting adb server on all interfaces :$ADB_PORT"
  setsid nohup adb -a -P "$ADB_PORT" nodaemon server >"$LOGDIR/adb-server.log" 2>&1 < /dev/null &
  for _ in $(seq 20); do ss -ltn | grep -q ":$ADB_PORT " && return; sleep 0.5; done
  log "adb server failed to start"; exit 1
}

start_emulators() {
  for i in $(seq 1 "$POOL_SIZE"); do
    local name="ghost_seed_$i" port=$((5552 + 2 * i))   # emulator-5554, -5556, ...
    if pgrep -f -- "-avd $name( |$)" >/dev/null; then continue; fi
    guard_load
    log "starting $name on emulator-$port"
    setsid nohup emulator -avd "$name" -port "$port" -no-window -no-audio -no-boot-anim \
      -gpu swiftshader_indirect -accel on -no-snapshot-save -camera-back emulated \
      -camera-front emulated >"$LOGDIR/$name.log" 2>&1 < /dev/null &
  done
  for i in $(seq 1 "$POOL_SIZE"); do
    local serial="emulator-$((5552 + 2 * i))"
    log "waiting for $serial to boot"
    for _ in $(seq 180); do
      [[ "$(adb -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]] && break
      sleep 2
    done
    # Quiet defaults for automation: no animations, stay awake, no lock screen, and no
    # heads-up notifications (their smart-reply chips sit where taps land and can send SMS).
    adb -s "$serial" shell 'settings put global window_animation_scale 0;
      settings put global transition_animation_scale 0;
      settings put global animator_duration_scale 0;
      settings put global stay_on_while_plugged_in 7;
      settings put system screen_off_timeout 1800000;
      settings put global heads_up_notifications_enabled 0;
      locksettings set-disabled true; input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard' \
      >/dev/null 2>&1 || true
  done
}

case "$CMD" in
  up)     install_sdk; create_avds; start_adb_server; start_emulators; adb devices -l; log "load $(load1)" ;;
  status) adb devices -l 2>/dev/null || true; log "load $(load1)"; pgrep -af qemu-system | cut -c1-120 || true ;;
  stop)   for s in $(adb devices | awk '/^emulator-/{print $1}'); do adb -s "$s" emu kill || true; done ;;
  *)      echo "usage: $0 [up|status|stop]"; exit 2 ;;
esac
