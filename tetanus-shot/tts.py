"""Synthesize narration clips with edge-tts and build timeline.json + voice.wav.

Usage: python3 tts.py [--force]
"""
import asyncio
import json
import os
import subprocess
import sys

import edge_tts

from script_data import (GAP_LINE, GAP_SCENE, LEAD_IN, RATE, SCENES, TAIL,
                         VOICE)

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
CLIPS = os.path.join(BUILD, "clips")
SR = 48000
TARGET_LUFS = -16.0
CLIP_LUFS = -26.0  # per-clip leveling so every sentence sits at the same level


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path])
    return float(out)


def measure_loudness(path):
    """Return (integrated LUFS, true peak dBTP) using ffmpeg's ebur128."""
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
         "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    summary = err[err.rindex("Summary:"):]
    integrated = float(summary.split("I:")[1].split("LUFS")[0])
    peak = float(summary.split("Peak:")[1].split("dBFS")[0])
    return integrated, peak


async def synth(text, path):
    for attempt in range(5):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(path)
            return
        except Exception:
            if attempt == 4:
                raise
            await asyncio.sleep(2 ** attempt)


def clean_clip(src, dst):
    """Decode to 48 kHz mono float WAV, trim edge silence, de-click fades."""
    trim = ("silenceremove=start_periods=1:start_threshold=-55dB:"
            "start_silence=0.02,areverse,"
            "silenceremove=start_periods=1:start_threshold=-55dB:"
            "start_silence=0.06,areverse")
    run(["ffmpeg", "-y", "-i", src, "-af",
         f"aresample={SR}:resampler=soxr:precision=28,highpass=f=60,{trim}",
         "-ac", "1", "-c:a", "pcm_f32le", dst])
    d = duration(dst)
    tmp = dst + ".tmp.wav"
    run(["ffmpeg", "-y", "-i", dst, "-af",
         f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.03):.4f}:d=0.03",
         "-c:a", "pcm_f32le", tmp])
    os.replace(tmp, dst)
    integrated, _ = measure_loudness(dst)
    run(["ffmpeg", "-y", "-i", dst, "-af",
         f"volume={CLIP_LUFS - integrated:.3f}dB", "-c:a", "pcm_f32le", tmp])
    os.replace(tmp, dst)
    return duration(dst)


def main():
    force = "--force" in sys.argv
    os.makedirs(CLIPS, exist_ok=True)

    timeline = {"scenes": [], "lines": []}
    t = LEAD_IN
    idx = 0
    for si, scene in enumerate(SCENES):
        if si > 0:
            t += GAP_SCENE - GAP_LINE
        scene_start = t
        for li, line in enumerate(scene["lines"]):
            mp3 = os.path.join(CLIPS, f"{idx:02d}.mp3")
            wav = os.path.join(CLIPS, f"{idx:02d}.wav")
            if force or not os.path.exists(mp3):
                asyncio.run(synth(line["zh"], mp3))
            d = clean_clip(mp3, wav)
            timeline["lines"].append({
                "idx": idx, "scene": si, "line": li, "cue": line["cue"],
                "zh": line["zh"], "en": line["en"],
                "start": round(t, 3), "end": round(t + d, 3), "wav": wav,
            })
            print(f"[{idx:02d}] {t:7.2f}s +{d:5.2f}s  {line['zh']}")
            t += d + GAP_LINE
            idx += 1
        timeline["scenes"].append({"idx": si, "id": scene["id"],
                                   "start": round(scene_start, 3),
                                   "end": round(t - GAP_LINE, 3)})
    total = t - GAP_LINE + TAIL
    timeline["duration"] = round(total, 3)

    # Scene boundaries: each scene visually spans until the next begins.
    for i, sc in enumerate(timeline["scenes"]):
        sc["vis_start"] = 0.0 if i == 0 else timeline["scenes"][i - 1]["vis_end"]
        if i + 1 < len(timeline["scenes"]):
            nxt = timeline["scenes"][i + 1]["start"]
            sc["vis_end"] = round((sc["end"] + nxt) / 2, 3)
        else:
            sc["vis_end"] = timeline["duration"]

    # Mix: place every clip at its start time on a silent bed.
    inputs, filters = [], []
    for n, ln in enumerate(timeline["lines"]):
        inputs += ["-i", ln["wav"]]
        ms = int(round(ln["start"] * 1000))
        filters.append(f"[{n}:a]adelay={ms}:all=1[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(len(timeline["lines"])))
    filters.append(f"{mix}amix=inputs={len(timeline['lines'])}:normalize=0,"
                   f"apad,atrim=0:{total:.3f}[mix]")
    raw = os.path.join(BUILD, "voice_raw.wav")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[mix]", "-ar", str(SR), "-ac", "1", "-c:a", "pcm_f32le", raw])

    # Loudness: TTS output has a ~24 dB crest factor, too peaky to reach
    # -16 LUFS without clipping. Allpass phase rotation (broadcast trick)
    # tames waveform asymmetry, a 4x-oversampled lookahead limiter on the
    # raw signal shaves the remaining transients, then a static gain lands
    # the integrated loudness on target with true peak below -1.5 dBTP.
    out = os.path.join(BUILD, "voice.wav")
    phase_rot = ",".join(f"allpass=f={f}:t=q:w=0.6" for f in (120, 240, 480, 960))
    integrated, _ = measure_loudness(raw)
    gain = TARGET_LUFS - integrated + 1.5
    for _ in range(4):
        chain = (f"{phase_rot},aresample={SR * 4},"
                 "alimiter=limit=0.3:attack=1:release=50:level=disabled,"
                 f"aresample={SR}:resampler=soxr,volume={gain:.3f}dB")
        run(["ffmpeg", "-y", "-i", raw, "-af", chain,
             "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", out])
        integrated, peak = measure_loudness(out)
        if abs(integrated - TARGET_LUFS) < 0.15:
            break
        gain += TARGET_LUFS - integrated
    print(f"voice.wav: {integrated:.1f} LUFS, true peak {peak:.1f} dBTP")

    with open(os.path.join(BUILD, "timeline.json"), "w") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=1)
    print(f"total duration {total:.2f}s")


if __name__ == "__main__":
    main()
