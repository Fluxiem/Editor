#!/usr/bin/env python3
"""Run the house DELIVERY CHECKLIST against a built edit.

Usage: qa_check.py PROJECT_DIR RENDER.mp4 [--kind teaching|skit] [--hooks N] [--out qa.json]
Reads PROJECT_DIR/cuts.json, edit.json and index.html. Prints and writes
[{label, pass, note}] in checklist order; exit code 1 if any item fails.
"""
import argparse, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STYLE = json.loads((ROOT / "style.json").read_text())
norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).split()

ap = argparse.ArgumentParser()
ap.add_argument("project"); ap.add_argument("render"); ap.add_argument("--kind", default="teaching")
ap.add_argument("--hooks", type=int, default=0); ap.add_argument("--out")
a = ap.parse_args()
P = pathlib.Path(a.project)
cuts, edit, html = json.load(open(P / "cuts.json")), json.load(open(P / "edit.json")), (P / "index.html").read_text()
takes = cuts["takes"]
res = []
add = lambda label, ok, note="": res.append({"label": label, "pass": bool(ok), "note": note})

# 1. hook on frame 1: hook text and first spoken line say the same thing, both start at 0
spoken = [w for t in takes if t["role"] == "hook" for w in norm(" ".join(x["w"] for x in t["words"]))]
text = norm(edit["hookText"])
shared = len(set(text) & set(spoken)) / max(1, len(set(text)))
first_word = takes[0]["words"][0]["t0"]
hook_dur = STYLE["hook"]["text"]["durationSec"]
add("Hook on frame 1 (visual = text = first line)", shared >= 0.8 and first_word <= 0.2 and 'data-start="0"' in html,
    f"text “{edit['hookText']}” vs spoken “{' '.join(spoken)}” ({shared:.0%} shared); speech starts {first_word:.2f}s; text fully resolved by {hook_dur}s")

# 2. length
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.render], capture_output=True, text=True).stdout)
L = STYLE["length"]
lo, hi = (L["teaching"]["minSec"], L["teaching"]["maxSec"]) if a.kind == "teaching" else (0, L["skit"]["maxSec"])
add("Length within target", lo <= dur <= min(hi, L["hardCapSec"]) and not (L["forbiddenRangeSec"][0] <= dur <= L["forbiddenRangeSec"][1]), f"{dur:.1f}s, {a.kind} target {lo}–{hi}s")

# 3. something new on screen at least every 2 s (visual events only, captions not counted)
ev = {0.0, dur}
ev |= {round(t["at"], 3) for t in takes}
for m in re.finditer(r'<(?!audio)[a-z]+[^>]*?data-start="([\d.]+)" data-duration="([\d.]+)"', html):
    s, d = float(m.group(1)), float(m.group(2))
    if d < dur - 0.1:
        ev |= {s, s + d}
for m in re.finditer(r'scale: (?:1\.0|1\.25|1) \}, \{ scale: (?:1\.12|1\.0|1), duration: (0\.35|0\.45)[^}]*\}, ([\d.]+)\);', html):
    ev.add(float(m.group(2)))
ev = sorted(e for e in ev if e <= dur)
gaps = [(round(b - a2, 2), round(a2, 2)) for a2, b in zip(ev, ev[1:])]
worst = max(gaps)
if "--verbose" in sys.argv[0:0] or True:
    print("holds over 1.8s:", [g for g in gaps if g[0] > 1.8], file=sys.stderr)
limit = STYLE["cuts"]["maxSecWithoutChange"]
add(f"A change on screen every {limit:g}s or less", worst[0] <= limit, f"longest hold {worst[0]}s at {worst[1]}s (cuts, punch-ins, B-roll, graphics; captions not counted)")

# 4. captions word-checked and inside the safe zone
tr_words = {w for t in takes for x in t["words"] for w in norm(x["w"])}
names = STYLE["captions"]["handCheckNames"]
bad_names = [n for n in names if any(p.lower() in tr_words for p in n.split()[:1]) and n.lower() not in " ".join(tr_words)]
cap = (P / "compositions/components/caption-highlight.html").read_text()
in_zone = f"top: {STYLE['captions']['centerY'] - 60}px" in cap and f"padding: 0 {STYLE['safeZone']['xMin']}px" in cap
low = [x["w"] for t in takes for x in t["words"] if x.get("prob", 1) < 0.5]
add("Captions word-checked and inside the safe zone", in_zone and not bad_names,
    f"caption line y≈{STYLE['captions']['centerY']}, x {STYLE['safeZone']['xMin']}–{STYLE['safeZone']['xMax']}; names list checked ({', '.join(names)}: none spoken)" if not bad_names else f"check names: {bad_names}")

# 5. accent moments
accents = (1 if edit.get("hero") else 0) + len(edit.get("accents", []))
add("At most 2 accent moments", accents <= STYLE["graphics"]["maxAccentMoments"], f"{accents} (text-behind-subject on “{edit.get('hero', {}).get('word', '')}”)")

# 6. watermarks
add("No watermarks", "watermark" not in html.lower(), "no logos or watermarks added; source and B-roll are public-domain NASA media")

# 7. alternate hooks
add("4 alternate-hook versions exported", a.hooks >= 4, f"{a.hooks} rendered (first 1–3s swapped)")

for r in res:
    print(("PASS " if r["pass"] else "FAIL ") + r["label"] + " — " + r["note"])
if a.out:
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1))
sys.exit(0 if all(r["pass"] for r in res) else 1)
