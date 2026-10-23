#!/usr/bin/env python3
"""Cut the people out of a stretch of the A-roll, for text or a logo behind the subjects.

Usage: matte.py AROLL.mp4 OUT.webm --start S --end E [--fps 30]
Writes a VP9 WebM with alpha (people opaque, everything else transparent), the same size as
the A-roll, starting at S. Masks come from rembg u2net_human_seg run on a downscaled copy of
each frame, then scaled back up and feathered, so it stays quick on 1080p and 4K.

edit.sh step e calls it once per span in <format>/cutout.json ({"spans": [{start, end, file}]}:
the behind-subject hero word and every "behind" motion-graphic scene) and skips spans whose
cutout_<i>.webm is newer than the A-roll with a matching cutout_<i>.span. ffmpeg runs with
-nostdin so it never eats the span list edit.sh feeds the loop.
"""
import argparse, pathlib, subprocess, tempfile
import numpy as np
from PIL import Image, ImageFilter
from rembg import new_session, remove

ap = argparse.ArgumentParser()
ap.add_argument("aroll"); ap.add_argument("out")
ap.add_argument("--start", type=float, required=True); ap.add_argument("--end", type=float, required=True)
ap.add_argument("--fps", type=int, default=30)
a = ap.parse_args()

session = new_session("u2net_human_seg")
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(a.start), "-to", str(a.end), "-i", a.aroll,
                    "-vf", f"fps={a.fps}", str(tmp / "f_%05d.png")], check=True)
    frames = sorted(tmp.glob("f_*.png"))
    for f in frames:
        img = Image.open(f).convert("RGB")
        small = img.copy(); small.thumbnail((640, 640))
        m = remove(small, session=session, only_mask=True, post_process_mask=True)
        m = m.resize(img.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
        rgba = img.copy(); rgba.putalpha(m)
        rgba.save(tmp / f.name.replace("f_", "c_"))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(tmp / "c_%05d.png"),
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "6M", "-auto-alt-ref", "0", a.out], check=True)
print(f"{len(frames)} frames -> {a.out}")
