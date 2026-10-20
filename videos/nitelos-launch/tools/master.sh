#!/usr/bin/env bash
# Master a rendered film: measured loudness to about -16 LUFS integrated with a true peak
# at or below -1 dBTP, then bake a poster frame into frame 0 (thumbnail grabbers use it).
#   tools/master.sh <raw.mp4> <out.mp4> <poster-seconds|none> [poster.jpg]
# Video frames are re-encoded only for the frame-0 overlay (crf 18); audio is AAC 192k.
set -euo pipefail
raw="$1"; out="$2"; poster_t="$3"; poster_jpg="${4:-}"
measure() { ffmpeg -hide_banner -nostats -i "$1" -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p'; }
input_i=$(measure "$raw" | sed -n 's/.*"input_i" : "\(.*\)".*/\1/p')
gain=$(awk -v i="$input_i" 'BEGIN { printf "%.2f", -16 - i }')
echo "measured ${input_i} LUFS, applying ${gain} dB with a -1.5 dBFS limiter"
tmp="${out%.mp4}.tmp.mp4"
ffmpeg -v error -y -i "$raw" -c:v copy -af "volume=${gain}dB,alimiter=limit=0.84:attack=5:release=60:level=disabled" -c:a aac -b:a 192k "$tmp"
if [ "$poster_t" != "none" ]; then
  jpg="${poster_jpg:-${out%.mp4}.poster.jpg}"
  ffmpeg -v error -y -ss "$poster_t" -i "$tmp" -frames:v 1 -q:v 2 "$jpg"
  ffmpeg -v error -y -i "$tmp" -i "$jpg" -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" \
    -map "[v]" -map 0:a? -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -movflags +faststart "$out"
  rm -f "$tmp"
else
  ffmpeg -v error -y -i "$tmp" -c copy -movflags +faststart "$out" && rm -f "$tmp"
fi
measure "$out" | grep -E '"input_(i|tp|lra)"'
