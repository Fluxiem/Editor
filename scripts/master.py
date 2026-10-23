#!/usr/bin/env python3
"""Master a render's audio to the delivery loudness, leaving the picture untouched.

Usage: master.py RENDER.mp4 [--lufs -14] [--tp -1.5]
The HyperFrames mix lands a few dB under the A-roll (it leaves headroom for SFX and music), so
step f runs this on every render: two-pass loudnorm (measure, then a linear gain to the target
with a true-peak limiter), AAC 192k, video stream copied. The file is replaced in place and the
before/after loudness is printed.
"""
import argparse, json, os, re, subprocess

ap = argparse.ArgumentParser(); ap.add_argument("render")
ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--tp", type=float, default=-1.5)
a = ap.parse_args()
target = f"I={a.lufs}:TP={a.tp}:LRA=11"

err = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", a.render, "-vn", "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                     capture_output=True, text=True).stderr
m = json.loads(re.findall(r"\{[^{}]*\}", err)[-1])
af = (f"loudnorm={target}:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
      f":measured_thresh={m['input_thresh']}:offset={m['target_offset']},aresample=48000")
tmp = a.render + ".master.mp4"
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", a.render, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", af,
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp], check=True)
os.replace(tmp, a.render)
out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", a.render, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
I = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1]; P = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", out)[-1]
print(f"mastered {a.render}: {m['input_i']} -> {I} LUFS, true peak {P} dBTP")
