#!/usr/bin/env bash
# Full rebuild: narration -> visuals -> final MP4.
set -euo pipefail
cd "$(dirname "$0")"

OUT="${1:-radiation_muscle_bilingual_vo.mp4}"

python3 tts.py "${TTS_ARGS:-}"
python3 render.py

ffmpeg -y -v error -i build/video.mp4 -i build/voice.wav \
  -map 0:v:0 -map 1:a:0 -c:v copy \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart -shortest "$OUT"

ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,sample_rate,channels \
  -show_entries format=duration,size -of default=nw=1 "$OUT"
ffmpeg -hide_banner -nostats -i "$OUT" -map 0:a -af ebur128=peak=true -f null - 2>&1 \
  | sed -n '/Summary:/,$p'

# Chat-friendly copy (< 4 MB): 720p, grain removed, two-pass low bitrate.
SMALL="${SMALL:-radiation_muscle_small.mp4}"
ffmpeg -y -v error -i "$OUT" -vf "scale=1280:720:flags=lanczos,hqdn3d=3:3:6:6" \
  -c:v libx264 -preset slow -b:v 120k -pass 1 -passlogfile build/small -an -f mp4 /dev/null
ffmpeg -y -v error -i "$OUT" -vf "scale=1280:720:flags=lanczos,hqdn3d=3:3:6:6" \
  -c:v libx264 -preset slow -b:v 120k -pass 2 -passlogfile build/small \
  -c:a aac -b:a 48k -ar 48000 -ac 2 -movflags +faststart "$SMALL"
ffprobe -v error -show_entries stream=codec_name,width,height \
  -show_entries format=duration,size -of default=nw=1 "$SMALL"
