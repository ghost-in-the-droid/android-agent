#!/usr/bin/env bash
#
# record-av.sh — turn a QuickTime iPhone screen recording (screen + the phone's
# real SYSTEM AUDIO) into the pipeline-ready demo MP4.
#
# Why QuickTime and not WDA MJPEG: the demo needs the phone's actual audio (an app
# talking, TTS, notifications). WDA MJPEG (:9100) is video-only, and the iPhone
# only exposes to the Mac as a screen-capture device via CoreMediaIO — which is
# exactly what QuickTime records. Since a demo is a RECORDING (not a live stream),
# latency is irrelevant, so we use this crisp full-res + audio path.
#
# CAPTURE (manual, ~1 min, in your GUI session):
#   1. QuickTime Player  >  File  >  New Movie Recording
#   2. Click the  ⌄  next to the red record button  ->  select your iPhone for
#      BOTH "Camera" and "Microphone" (the iPhone screen + audio then appear)
#   3. Hit record, run the demo (the agent drives the phone), hit stop
#   4. File > Save  (e.g. ~/Desktop/duolingo.mov)
#
# THEN transcode to the pipeline mp4:
#   scripts/ios/record-av.sh ~/Desktop/duolingo.mov
#   scripts/ios/record-av.sh                 # auto-picks the newest .mov in ~/Desktop, ~/Movies
#
# Output: /tmp/ios_demo_rec.mp4 (or --out PATH) — H.264 High, yuv420p, 30fps,
# AAC audio, portrait, even dimensions. Full-res/crisp by default (composite
# downscales with Lanczos); pass --half for a ~half-res, smaller file.
set -uo pipefail

IN=""; OUT="/tmp/ios_demo_rec.mp4"; HALF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --half) HALF=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) IN="$1"; shift ;;
  esac
done

if [ -z "$IN" ]; then
  IN="$(ls -t "$HOME"/Desktop/*.mov "$HOME"/Movies/*.mov 2>/dev/null | head -1)"
  [ -n "$IN" ] && echo "[record-av] auto-selected newest recording: $IN"
fi
[ -f "$IN" ] || { echo "ERROR: no input .mov. Record one in QuickTime (see --help) or pass a path."; exit 1; }

# even dimensions for libx264; optional half-scale. fps=30 to match the pipeline.
if [ -n "$HALF" ]; then
  VF="scale=trunc(iw/4)*2:trunc(ih/4)*2,fps=30"
else
  VF="scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30"
fi

echo "[record-av] transcoding $IN -> $OUT  (crisp H.264 High + AAC audio, 30fps${HALF:+, half-res})"
ffmpeg -y -loglevel warning -i "$IN" \
  -vf "$VF" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 18 -preset slow \
  -c:a aac -b:a 192k -movflags +faststart \
  "$OUT"

if [ -s "$OUT" ]; then
  echo "[record-av] saved $OUT ($(stat -f%z "$OUT") bytes)"
  echo "[record-av] streams:"; ffprobe -v error -show_entries stream=codec_type,codec_name,width,height -of default=nw=1 "$OUT" 2>/dev/null | sed 's/^/   /'
  ffprobe -v error -select_streams a -show_entries stream=codec_name "$OUT" 2>/dev/null | grep -q . \
    && echo "[record-av] ✅ audio track present" \
    || echo "[record-av] ⚠️  NO audio track — did you pick the iPhone as the Microphone in QuickTime?"
else
  echo "[record-av] ❌ transcode produced no file"; exit 1
fi
