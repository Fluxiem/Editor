#!/usr/bin/env python3
"""Where is the speaker? Samples frames and reports the subject's horizontal centre.

Usage: subject_track.py CLIP OUT.json [--every 2.0]
Writes [{"t": sec, "cx": 0..1 or null, "top": 0..1 or null, "area": 0..1}] using rembg
u2net_human_seg on downscaled frames (cx = mask centroid x, top = highest subject row).
Used to aim the 9:16 crop and to place behind-subject text.
"""
import argparse, json, subprocess, tempfile, pathlib
import numpy as np
from PIL import Image
from rembg import new_session, remove

ap = argparse.ArgumentParser(); ap.add_argument("clip"); ap.add_argument("out"); ap.add_argument("--every", type=float, default=2.0)
a = ap.parse_args()
s = new_session("u2net_human_seg")
res = []
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["ffmpeg", "-v", "error", "-i", a.clip, "-vf", f"fps=1/{a.every},scale=480:-2", f"{tmp}/f_%05d.png"], check=True)
    for i, f in enumerate(sorted(pathlib.Path(tmp).glob("f_*.png"))):
        m = np.asarray(remove(Image.open(f), session=s, only_mask=True)) > 127
        area = float(m.mean())
        if area < 0.02:
            res.append({"t": round(i * a.every, 2), "cx": None, "top": None, "area": round(area, 4)}); continue
        ys, xs = np.nonzero(m)
        res.append({"t": round(i * a.every, 2), "cx": round(float(xs.mean()) / m.shape[1], 4), "top": round(float(ys.min()) / m.shape[0], 4), "area": round(area, 4)})
pathlib.Path(a.out).write_text(json.dumps(res))
print(len(res), "samples")
