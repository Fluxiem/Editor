#!/usr/bin/env python3
"""Analyse a reference reel so the edit can match it.

Usage: analyze_ref.py REF.mp4 OUT_DIR
Writes OUT_DIR/ref_report.json and two contact sheets for visual review:
  hook.jpg   first 3 s at 8 fps (hook framing, first text, how it animates in)
  reel.jpg   1 frame per second (text styles/placement, captions, transitions, zooms)
Measured: shot cuts (scene change > 0.3), shots/sec, median and mean shot length, the hook
window's cuts, spoken words in the first 3 s and overall pace, loudness. Text styles,
placement, transitions and zooms are read from the sheets and written into the edit spec as
overrides (see CLAUDE.md, "References").
"""
import json, pathlib, re, statistics, subprocess, sys
import numpy as np

src, out = sys.argv[1], pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
run = lambda *a: subprocess.run(a, capture_output=True, text=True)

dur = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src).stdout)
vs = json.loads(run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", src).stdout)["streams"][0]

# shot cuts (0.3 = hard cuts between different shots; 0.12 also catches jump cuts within a take)
def scene_cuts(th):
    log = run("ffmpeg", "-hide_banner", "-i", src, "-vf", f"select='gt(scene,{th})',showinfo", "-an", "-f", "null", "-").stderr
    return [round(float(t), 3) for t in re.findall(r"pts_time:([\d.]+)", log)]
cuts, jump_cuts = scene_cuts(0.3), scene_cuts(0.12)
edges = [0.0] + cuts + [dur]
shots = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.05]

# speech
words = []
try:
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    segs, _ = WhisperModel("small.en", device="cpu", compute_type="int8").transcribe(np.frombuffer(pcm, dtype=np.float32), word_timestamps=True)
    words = [{"w": w.word.strip(), "t0": round(w.start, 2), "t1": round(w.end, 2)} for s in segs for w in (s.words or [])]
except Exception as e:  # reference may be music-only
    print("transcription skipped:", e, file=sys.stderr)

loud = run("ffmpeg", "-hide_banner", "-i", src, "-af", "loudnorm=print_format=json", "-f", "null", "-").stderr
lufs = json.loads(loud[loud.rindex("{"):loud.rindex("}") + 1]) if "{" in loud else {}

# contact sheets
run("ffmpeg", "-v", "error", "-y", "-t", "3", "-i", src, "-vf", "fps=8,scale=216:-2,tile=8x3", "-frames:v", "1", str(out / "hook.jpg"))
cols = 10
rows = max(1, int(dur) // cols + 1)
run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"fps=1,scale=180:-2,tile={cols}x{rows}", "-frames:v", "1", str(out / "reel.jpg"))

report = {
    "source": src, "durationSec": round(dur, 2), "size": [vs["width"], vs["height"]], "fps": vs["r_frame_rate"],
    "cuts": cuts, "shots": len(shots),
    "medianShotSec": round(statistics.median(shots), 2) if shots else None,
    "meanShotSec": round(statistics.mean(shots), 2) if shots else None,
    "cutsInFirst3s": sum(1 for c in cuts if c < 3),
    "jumpCuts": len(jump_cuts), "secPerChangeIncludingJumpCuts": round(dur / (len(jump_cuts) + 1), 2),
    "hookWords": " ".join(w["w"] for w in words if w["t0"] < 3),
    "firstWordAt": words[0]["t0"] if words else None,
    "wordsPerMin": round(len(words) / dur * 60, 1) if words else 0,
    "loudness": {k: lufs.get(k) for k in ("input_i", "input_tp")},
    "sheets": {"hook": str(out / "hook.jpg"), "reel": str(out / "reel.jpg")},
}
(out / "ref_report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: v for k, v in report.items() if k not in ("cuts",)}, indent=1))
