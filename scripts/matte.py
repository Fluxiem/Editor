#!/usr/bin/env python3
"""Per-frame subject matte for the text-behind-subject shot.

Usage: matte.py CLIP OUT_DIR --start S --end E [--fps 30]
Writes OUT_DIR/matte_%05d.png (white = subject) and OUT_DIR/matte.webm (alpha mask video)
using rembg u2net_human_seg.
"""
import argparse, pathlib, subprocess, tempfile
from PIL import Image
from rembg import new_session, remove

ap = argparse.ArgumentParser()
ap.add_argument("clip"); ap.add_argument("out")
ap.add_argument("--start", type=float, required=True); ap.add_argument("--end", type=float, required=True)
ap.add_argument("--fps", type=int, default=30)
a = ap.parse_args()

out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
session = new_session("u2net_human_seg")
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a.start), "-to", str(a.end), "-i", a.clip,
                    "-vf", f"fps={a.fps}", f"{tmp}/f_%05d.png"], check=True)
    frames = sorted(pathlib.Path(tmp).glob("f_*.png"))
    for f in frames:
        remove(Image.open(f), session=session, only_mask=True, post_process_mask=True).save(out / f.name.replace("f_", "matte_"))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(out / "matte_%05d.png"),
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(out / "matte.webm")], check=True)
print(f"{len(frames)} matte frames -> {out}")
