#!/usr/bin/env bash
# Placeholder demo assets for the showcase frontend (task #783), so /showcase
# renders before the record_demo.py pipeline (task #782) produces real demos.
# Each real demo overwrites its placeholder in place — same paths, same names.
set -euo pipefail

cd "$(dirname "$0")/../.."
BRAND_FONT="site/public/showcase/_brand/fonts/Outfit[wght].ttf"
BG="#070b08"

make_demo() {
  local slug="$1" title="$2"
  local dir="site/public/showcase/$slug"
  mkdir -p "$dir"
  ffmpeg -y -loglevel error \
    -f lavfi -i "color=c=${BG}:s=1280x720:d=6" \
    -vf "drawtext=fontfile='${BRAND_FONT}':text='${title}':fontcolor=0xe8ede9:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-40, \
         drawtext=fontfile='${BRAND_FONT}':text='placeholder — real demo ships with the showcase pipeline':fontcolor=0x8a9a8d:fontsize=28:x=(w-text_w)/2:y=(h)/2+40, \
         drawbox=x=(iw-180)/2:y=ih-120:w=180:h=6:color=0x00e5a0:t=fill" \
    -c:v libvpx-vp9 -b:v 0 -crf 40 -an "$dir/demo.webm"
  ffmpeg -y -loglevel error -i "$dir/demo.webm" -frames:v 1 "$dir/poster.png"
}

make_demo on-device-gemma "On-Device Gemma"
make_demo mcp-claude-code "Claude Code → Your Phone"
make_demo ios "iPhone Support"

# Hero reel placeholder
ffmpeg -y -loglevel error \
  -f lavfi -i "color=c=${BG}:s=1920x1080:d=8" \
  -vf "drawtext=fontfile='${BRAND_FONT}':text='Ghost in the Droid':fontcolor=0xe8ede9:fontsize=110:x=(w-text_w)/2:y=(h-text_h)/2-60, \
       drawtext=fontfile='${BRAND_FONT}':text='hero reel placeholder':fontcolor=0x8a9a8d:fontsize=36:x=(w-text_w)/2:y=(h)/2+60" \
  -c:v libvpx-vp9 -b:v 0 -crf 42 -an site/public/showcase/hero-reel.webm
ffmpeg -y -loglevel error -i site/public/showcase/hero-reel.webm -frames:v 1 site/public/showcase/hero-poster.png

echo "placeholders written"
