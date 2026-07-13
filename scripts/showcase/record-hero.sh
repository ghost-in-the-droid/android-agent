#!/usr/bin/env bash
# Record a synced "hero" demo: a real Claude Code TUI driving the iPhone over
# wireless direct-WDA (Tailscale, no USB, no Appium), with the phone screen
# captured in parallel and composited side-by-side.
#
# Usage: record-hero.sh "<natural task prompt>" [out-basename]
set -uo pipefail

PROMPT="${1:?usage: record-hero.sh \"<prompt>\" [out]}"
OUT="${2:-hero}"
DIR="${HERO_DIR:-/tmp/ghost-ios/hero}"
UDID="${IOS_DEVICE_UDID:-00008130-001259DC11C2001C}"
TSIP="${IOS_TS_IP:-100.78.142.68}"
BASE="http://${TSIP}:8100"
REPO="/Users/christianloan/Agent/ghost-mirror"
MCP="${HERO_MCP:-${DIR}/.mcp.json}"
COLS="${HERO_COLS:-100}"; ROWS="${HERO_ROWS:-30}"
mkdir -p "$DIR"
CAST="$DIR/${OUT}.cast"; PHONE="$DIR/${OUT}-phone.mp4"
TERM_MP4="$DIR/${OUT}-term.mp4"; GIF="$DIR/${OUT}-term.gif"
FINAL="$DIR/${OUT}-final.mp4"; FIFO="$DIR/${OUT}.mjpeg.fifo"

say(){ printf '\033[1;36m[hero]\033[0m %s\n' "$*"; }

curl -sf -m3 "$BASE/status" >/dev/null 2>&1 || { say "WDA down at $BASE — bring it up first"; exit 1; }
say "WDA up at $BASE (wireless)"

# 1) capture session with the MJPEG server enabled
SID=$(curl -sf -m5 -X POST "$BASE/session" -H 'Content-Type: application/json' \
  -d '{"capabilities":{"alwaysMatch":{"platformName":"iOS","appium:mjpegServerPort":9100}}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('sessionId') or d['value']['sessionId'])" 2>/dev/null)
[ -n "$SID" ] || { say "could not create capture session"; exit 1; }
curl -sf -m4 -X POST "$BASE/session/$SID/appium/settings" -H 'Content-Type: application/json' \
  -d '{"settings":{"mjpegServerFramerate":24,"mjpegServerScreenshotQuality":45,"mjpegScalingFactor":70}}' >/dev/null 2>&1
say "capture session ${SID:0:8} (mjpeg :9100)"

# 2) keepalive so neither WDA nor the mjpeg session idles during the run
( for i in $(seq 1 220); do curl -sf -m2 "$BASE/status" >/dev/null 2>&1
  curl -sf -m2 "$BASE/session/$SID/window/size" >/dev/null 2>&1
  curl -s -m1 -o /dev/null http://192.0.2.1/ 2>/dev/null; done ) & KA=$!

# 3) phone capture via a fifo so we hold ffmpeg's real pid (SIGINT finalizes mp4)
rm -f "$FIFO"; mkfifo "$FIFO"
curl -sN "http://${TSIP}:9100" > "$FIFO" & CURL=$!
ffmpeg -y -loglevel error -f mpjpeg -i "$FIFO" -an \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -r 24 -c:v libx264 -pix_fmt yuv420p "$PHONE" & FF=$!
say "phone capture -> $PHONE (ffmpeg pid $FF)"
sleep 1.5

# 4) record the Claude Code TUI (drives the phone via MCP over direct-WDA)
say "recording TUI (drives the phone)…"
START=$(python3 -c "import time;print(time.time())")
"${REPO}/.venv/bin/python" "${REPO}/scripts/showcase/claude_tui_driver.py" \
  --prompt "$PROMPT" --mcp-config "$MCP" --cast "$CAST" \
  --cols "$COLS" --rows "$ROWS" \
  --env IOS_WDA_DIRECT=1 --env "IOS_WDA_URL=${BASE}" >/dev/null 2>&1
END=$(python3 -c "import time;print(time.time())")
RUN=$(python3 -c "print(max(6,round($END-$START)+1))")
say "TUI done — active window ~${RUN}s"

# 5) stop captures (SIGINT ffmpeg directly so the mp4 finalizes)
kill -INT "$FF" 2>/dev/null; wait "$FF" 2>/dev/null
kill "$CURL" 2>/dev/null; kill "$KA" 2>/dev/null; rm -f "$FIFO"
curl -s -m3 -X DELETE "$BASE/session/$SID" >/dev/null 2>&1
say "captures stopped"

# 6) render terminal cast -> mp4
agg --theme monokai --font-size 18 --idle-time-limit 2 "$CAST" "$GIF" >/dev/null 2>&1
ffmpeg -y -loglevel error -i "$GIF" -movflags +faststart \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -pix_fmt yuv420p "$TERM_MP4"
say "terminal -> $TERM_MP4 ($(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$TERM_MP4" 2>/dev/null)s)"

# 7) composite: phone (trimmed to active window) left, terminal right, dark canvas
if [ -s "$PHONE" ] && [ -s "$TERM_MP4" ]; then
  ffmpeg -y -loglevel error -i "$PHONE" -i "$TERM_MP4" -filter_complex \
    "color=c=0x0d1117:s=1920x1080:d=${RUN}[bg];
     [0:v]trim=0:${RUN},setpts=PTS-STARTPTS,scale=-2:1000[ph];
     [1:v]setpts=PTS-STARTPTS,scale=1200:-2[tm];
     [bg][ph]overlay=90:(H-h)/2[a];
     [a][tm]overlay=610:(H-h)/2:shortest=1[v]" \
    -map "[v]" -r 24 -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$FINAL"
  say "FINAL -> $FINAL"; ls -l "$FINAL"
else
  say "phone/term video missing — phone=$(stat -f%z "$PHONE" 2>/dev/null||echo 0)B term=$(stat -f%z "$TERM_MP4" 2>/dev/null||echo 0)B"
fi
