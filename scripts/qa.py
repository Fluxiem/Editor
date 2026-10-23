#!/usr/bin/env python3
"""QA a finished render: frames to look at, plus the checks a machine can make.

Usage: qa.py RENDER.mp4 JOB_DIR [--format 9x16]
Writes JOB_DIR/qa/<render name>.jpg, a strip of frames at 0s, 2s, the middle and the end
(Claude reads it before anything is uploaded), JOB_DIR/qa/<render name>_cover.jpg (a cover frame:
0.8s into the first behind-subject span in <format>/cutout.json, the hero word or a "behind" scene,
else the resolved hook at 0.6s; old single {"start","end"} cutout.json files still work), and
prints/returns these checks:
size and fps match the format, H.264 yuv420p, length inside the target, audio present with
peaks at or under -1 dBFS, and the hook on screen at 0s (hook text set in edit.json).
Exit 1 if any check fails.
"""
import argparse, json, pathlib, re, subprocess, sys

SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "4x5": (1080, 1350), "1x1": (1080, 1080)}
ap = argparse.ArgumentParser(); ap.add_argument("render"); ap.add_argument("job"); ap.add_argument("--format", default="9x16")
a = ap.parse_args()
job = pathlib.Path(a.job)
cuts, edit = json.load(open(job / "cuts.json")), json.load(open(job / "edit.json"))

p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate",
                               "-of", "json", a.render], capture_output=True, text=True, check=True).stdout)
v = next(s for s in p["streams"] if s["codec_type"] == "video")
has_audio = any(s["codec_type"] == "audio" for s in p["streams"])
dur = float(p["format"]["duration"])
vol = subprocess.run(["ffmpeg", "-v", "info", "-i", a.render, "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
peak = float(re.search(r"max_volume: ([-\d.]+) dB", vol).group(1)) if has_audio else None
lo, hi = cuts.get("target", [30, 45])

out = job / "qa"; out.mkdir(exist_ok=True)
sheet = out / (pathlib.Path(a.render).stem + ".jpg")
times = [0.05, 2.0, dur / 2, max(0, dur - 0.2)]
W, H = SIZES[a.format]
th = 640 if H >= W else 360
inputs = sum((["-ss", f"{t:.2f}", "-i", a.render] for t in times), [])
subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                "".join(f"[{i}:v]scale=-2:{th},drawtext=text='{t:.1f}s':x=12:y=12:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.6[f{i}];" for i, t in enumerate(times))
                + "".join(f"[f{i}]" for i in range(len(times))) + f"hstack=inputs={len(times)}", "-frames:v", "1", str(sheet)], check=True)

cj = job / a.format / "cutout.json"   # {"spans": [{start, end, file}]} (or an old single {start, end})
spans = sorted((lambda d: d.get("spans", [d]))(json.loads(cj.read_text())), key=lambda s: s["start"]) if cj.exists() else []
cover_t = spans[0]["start"] + 0.8 if spans else 0.6
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{cover_t:.2f}", "-i", a.render, "-frames:v", "1", "-q:v", "2",
                str(out / (pathlib.Path(a.render).stem + "_cover.jpg"))], check=True)

checks = [
    ("Size and frame rate", (v["width"], v["height"]) == (W, H) and v["r_frame_rate"] == "30/1", f"{v['width']}x{v['height']} @ {v['r_frame_rate']}"),
    ("H.264 yuv420p", v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p", f"{v['codec_name']} {v['pix_fmt']}"),
    ("Length inside target", lo - 1 <= dur <= hi, f"{dur:.1f}s (target {lo:g}-{hi:g}s)"),
    ("Audio present, peaks <= -1 dBFS", has_audio and peak <= -1.0, f"peak {peak} dBFS" if has_audio else "no audio"),
    ("Hook text from frame 1", bool(edit.get("hookText")) and cuts["takes"][0]["role"] == "hook", f"“{edit.get('hookText', '')}”"),
]
for label, ok, note in checks:
    print(("PASS " if ok else "FAIL ") + f"{label}: {note}")
print(f"frames to check: {sheet}")
(out / (pathlib.Path(a.render).stem + ".json")).write_text(json.dumps([{"label": l, "pass": bool(o), "note": n} for l, o, n in checks], indent=1))
sys.exit(0 if all(o for _, o, _ in checks) else 1)
