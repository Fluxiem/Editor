#!/usr/bin/env python3
"""Word-level transcript for cutting and captions.

Usage: transcribe.py MEDIA OUT.json [--model small.en]
Writes {"words": [{"word", "start", "end", "prob"}], "segments": [...]} in seconds.
Names from style.json captions.handCheckNames are flagged for manual review.
"""
import argparse, json, pathlib, subprocess
import numpy as np
from faster_whisper import WhisperModel

ap = argparse.ArgumentParser()
ap.add_argument("media"); ap.add_argument("out"); ap.add_argument("--model", default="small.en")
a = ap.parse_args()

style = json.loads((pathlib.Path(__file__).resolve().parent.parent / "style.json").read_text())
names = style["captions"]["handCheckNames"]

# Decode with ffmpeg (handles MOV/HEVC) instead of faster-whisper's PyAV path.
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", a.media, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                     check=True, capture_output=True).stdout
audio = np.frombuffer(pcm, dtype=np.float32)

model = WhisperModel(a.model, device="cpu", compute_type="int8")
segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=False,
                                  initial_prompt=", ".join(names) + ".")
words, segs = [], []
for s in segments:
    segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()})
    for w in s.words or []:
        words.append({"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(w.probability, 3)})

pathlib.Path(a.out).write_text(json.dumps({"duration": info.duration, "words": words, "segments": segs}, indent=1))
low = [w for w in words if w["prob"] < 0.5]
print(f"{len(words)} words, {info.duration:.1f}s, {len(low)} low-confidence words to hand-check")
