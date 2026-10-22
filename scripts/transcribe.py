#!/usr/bin/env python3
"""Word-level transcript of every clip, for cutting and captions.

Usage: transcribe.py OUT.json CLIP [CLIP ...] [--model medium.en]
Writes {"clips": [{"file", "duration", "wpm"}], "words": [{"clip", "word", "start", "end", "prob"}]}
with times in seconds of each clip's own timeline. Clips with almost no speech (fewer than
style.json clipRoles.brollMaxWordsPerMin words a minute) are marked "broll": true.
Audio is decoded with ffmpeg to 16 kHz mono, so 4K/HEVC/MOV sources of any size are fine.
"""
import argparse, json, pathlib, subprocess
import numpy as np
from faster_whisper import WhisperModel

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("clips", nargs="+"); ap.add_argument("--model", default="medium.en")
a = ap.parse_args()

style = json.loads((pathlib.Path(__file__).resolve().parent.parent / "style.json").read_text())
names = style["captions"]["handCheckNames"]
model = WhisperModel(a.model, device="cpu", compute_type="int8")

clips, words = [], []
for path in a.clips:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    dur = len(audio) / 16000
    name = pathlib.Path(path).name
    if dur < 0.5:
        clips.append({"file": name, "duration": round(dur, 3), "wpm": 0, "broll": True}); continue
    segments, _ = model.transcribe(audio, word_timestamps=True, vad_filter=False, initial_prompt=", ".join(names) + ".")
    n = 0
    for s in segments:
        for w in s.words or []:
            words.append({"clip": name, "word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(w.probability, 3)})
            n += 1
    wpm = n / max(dur / 60, 1e-6)
    clips.append({"file": name, "duration": round(dur, 3), "wpm": round(wpm), "broll": wpm < style["clipRoles"]["brollMaxWordsPerMin"]})
    print(f"{name}: {n} words, {dur:.1f}s" + (" (B-roll)" if clips[-1]["broll"] else ""))

pathlib.Path(a.out).write_text(json.dumps({"clips": clips, "words": words}, indent=1))
low = [w["word"] for w in words if w["prob"] < 0.5]
print(f"{len(words)} words total, {len(low)} low-confidence words to hand-check")
