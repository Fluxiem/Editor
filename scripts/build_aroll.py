#!/usr/bin/env python3
"""Assemble the A-roll from cuts.json: graded, reframed, 30 fps, voice levelled.

Usage: build_aroll.py CUTS.json CLIP_DIR OUT.mp4 [--format 9x16|16x9|4x5|1x1] [--lut FILE.cube] [--voice off|light|strong]

Each take is read with a fast input seek (-ss before -i), so a 4K, 50 GB source never gets
decoded from the top: only the seconds that are used. Takes are encoded as separate segments
in a work folder next to OUT, then joined with the concat demuxer. Vertical formats crop
around the take's `focus` (0..1 across the source width; per speaker), wide keeps the frame.
Audio gets 10 ms fades at every cut, a voice clean-up (rumble high-pass, light FFT denoise,
gentle compression; style.json studio.audio.voiceClean, default light), then loudnorm to
-14 LUFS, true peak -6 dBFS.
"""
import argparse, json, pathlib, shutil, subprocess

SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "4x5": (1080, 1350), "1x1": (1080, 1080), "4x3": (1440, 1080)}
ap = argparse.ArgumentParser()
ap.add_argument("cuts"); ap.add_argument("clips"); ap.add_argument("out")
ap.add_argument("--format", default="9x16", choices=SIZES); ap.add_argument("--lut")
ap.add_argument("--voice", choices=["off", "light", "strong"])
a = ap.parse_args()
style = json.loads((pathlib.Path(__file__).resolve().parent.parent / "style.json").read_text())
voice = a.voice or style.get("studio", {}).get("audio", {}).get("voiceClean", "light")
CLEAN = {"off": "",
         "light": "highpass=f=80,afftdn=nr=10:nf=-40,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150,",
         "strong": "highpass=f=90,afftdn=nr=18:nf=-35,deesser,acompressor=threshold=-22dB:ratio=3.5:attack=8:release=120,"}[voice]
OW, OH = SIZES[a.format]
out = pathlib.Path(a.out)
work = out.parent / f".work-{out.stem}"
shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
takes = json.load(open(a.cuts))["takes"]
probe = {}


def size(clip):
    if clip not in probe:
        s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                       "-of", "json", clip], check=True, capture_output=True, text=True).stdout)["streams"][0]
        probe[clip] = (s["width"], s["height"])
    return probe[clip]


lut = f"lut3d='{pathlib.Path(a.lut).resolve()}':interp=tetrahedral," if a.lut else ""
parts = []
for i, t in enumerate(takes):
    src = str(pathlib.Path(a.clips) / t["clip"])
    W, H = size(src)
    # largest crop of the output aspect that fits the source, centred on the focus point
    cw, ch = (W, round(W * OH / OW)) if W / H < OW / OH else (round(H * OW / OH), H)
    cw, ch = cw // 2 * 2, ch // 2 * 2
    x = min(max(0, round(t.get("focus", 0.5) * W - cw / 2)), W - cw)
    y = (H - ch) // 2
    d = t["out"] - t["in"]
    seg = work / f"{i:03d}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t['in']:.3f}", "-t", f"{d:.3f}", "-i", src,
                    "-vf", f"{lut}crop={cw}:{ch}:{x}:{y},scale={OW}:{OH}:flags=lanczos,fps=30,setsar=1,format=yuv420p",
                    "-af", f"aresample=48000,afade=t=in:d=0.01,afade=t=out:st={max(0, d - 0.01):.3f}:d=0.01",
                    "-ac", "2", "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-c:a", "pcm_s16le", "-f", "mov", str(seg)], check=True)
    parts.append(seg)
    print(f"  take {i + 1}/{len(takes)}  {t['clip']} {t['in']:.2f}-{t['out']:.2f}  crop x={x}")

(work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
                "-af", f"{CLEAN}loudnorm=I=-14:TP=-6:LRA=7,aresample=48000", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=True)
shutil.rmtree(work)
print(out)
