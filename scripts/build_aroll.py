#!/usr/bin/env python3
"""Cut and reframe the talking-head A-roll from a cut list.

Usage: build_aroll.py SOURCE CUTS.json TRACK.json OUT.mp4 [--hook CUTS_HOOK.json]
Each take is trimmed in source time, cropped 9:16 around the speaker (median subject
centre from TRACK.json over the take) and scaled to 1080x1920 at 30 fps. Audio gets 10 ms
fades at every cut, then the whole voice track is levelled (loudnorm, true peak -6 dBFS).
"""
import argparse, json, statistics, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("cuts"); ap.add_argument("track"); ap.add_argument("out")
a = ap.parse_args()

probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", a.src],
                                  check=True, capture_output=True, text=True).stdout)["streams"][0]
W, H = probe["width"], probe["height"]
cw = round(H * 9 / 16 / 2) * 2
track = [t for t in json.load(open(a.track)) if t["cx"] is not None]
takes = json.load(open(a.cuts))["takes"]

parts, labels = [], []
for i, t in enumerate(takes):
    near = [s["cx"] for s in track if t["in"] - 2 <= s["t"] <= t["out"] + 2] or [s["cx"] for s in track]
    x = min(max(0, round(statistics.median(near) * W - cw / 2)), W - cw)
    d = t["out"] - t["in"]
    parts.append(f"[0:v]trim={t['in']}:{t['out']},setpts=PTS-STARTPTS,crop={cw}:{H}:{x}:0,scale=1080:1920:flags=lanczos,fps=30,setsar=1[v{i}];"
                 f"[0:a]atrim={t['in']}:{t['out']},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,afade=t=out:st={max(0, d - 0.01):.3f}:d=0.01[a{i}];")
    labels.append(f"[v{i}][a{i}]")
fc = "".join(parts) + "".join(labels) + f"concat=n={len(takes)}:v=1:a=1[v][a0];[a0]loudnorm=I=-14:TP=-6:LRA=7,aresample=48000[a]"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out], check=True)
print(a.out)
