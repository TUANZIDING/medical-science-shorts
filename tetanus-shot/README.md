# 破伤风针，什么时候该打？ / Tetanus shots: when & why

A ~2¼-minute cinematic, bilingual (简体中文 + English captions) science-popularization
short for ordinary adults, with a Mandarin neural-TTS voiceover.

Output: `tetanus_shot_bilingual_vo.mp4` (1920×1080, 24 fps, H.264 + AAC 48 kHz stereo,
voice normalized to -16 LUFS integrated).

> 本视频仅供科普，具体请遵医嘱 / For education only; follow your clinician.

## How it is made

| File | Role |
| --- | --- |
| `script_data.py` | The narration script: scenes, lines (Chinese VO + zh/en captions), the visual cue per line, voice, speaking rate and pause lengths. Edit this to change the content. |
| `tts.py` | Synthesizes each line with **edge-tts** (`zh-CN-YunyangNeural`), resamples to 48 kHz (soxr), trims edge silence, de-clicks, levels every clip to the same loudness, places clips on a timeline, then masters to -16 LUFS (allpass phase rotation, 4×-oversampled lookahead limiter, static gain; true peak < -1.5 dBTP). Writes `build/voice.wav` and `build/timeline.json`. |
| `render.py` | Procedurally renders every frame (pycairo vector art + Pillow CJK text): graded gradient backgrounds with drifting light, bokeh and dust motes, line-art illustrations with glow, soft wipe text reveals, light-leak scene transitions, then a filmic grade (S-curve + teal/amber split tone), bloom, vignette and film grain. Renders in parallel chunks and encodes with libx264. Writes `build/video.mp4`. |
| `build.sh` | Runs everything and muxes the final MP4, then prints ffprobe info and the measured loudness. |

Captions are driven by the same `timeline.json` as the audio (each caption appears with
its own TTS clip), so they stay in sync with the narration by construction.

## Rebuild

Requirements: Python 3.10+, ffmpeg/ffprobe, network access (edge-tts calls Microsoft's
online neural TTS service).

```bash
sudo apt-get install -y ffmpeg fonts-noto-cjk python3-cairo
pip install edge-tts pillow numpy        # add --break-system-packages on Debian/Ubuntu

cd tetanus-shot
./build.sh                               # -> tetanus_shot_bilingual_vo.mp4
TTS_ARGS=--force ./build.sh              # also re-synthesize cached TTS clips
```

Preview individual frames without a full render:

```bash
python3 tts.py                           # needed once for build/timeline.json
python3 render.py --stills 5,24,64,112   # -> build/stills/t_XXX.XX.png
```

A full render takes a few minutes on 4 cores. `build/` holds intermediates and is not committed.

## Scenes

1. **Title**: 破伤风针 · 什么时候该打？为什么要打？
2. **01 什么是破伤风**: C. tetani bacteria (drumstick-shaped rods), sources (soil / dust / rust),
   toxin attacking a neuron (lockjaw, muscle spasms), cleaning alone may not be enough.
3. **02 什么时候该打**: four high-risk wound cards (punctures, soil/rust, animal bites, burns);
   booster timeline (routine ~10 years, dirty wounds > ~5 years); tell your doctor if unsure.
4. **03 为什么要打**: vaccine → antibodies shield; protection decays, boosters restore it; act promptly.
5. **04 注意事项**: six tips plus "don't self-decide; let a doctor decide".
6. **End card**: 小小一针，守护安心 + disclaimer.

Medical content is general guidance at a science-popularization level; intervals are phrased as
"about" and viewers are told to follow local clinicians.
