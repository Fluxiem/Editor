#!/usr/bin/env python3
"""Plan the cut from the transcript: the lines to keep, word-accurate, with every cut explained.

Usage: plan_cuts.py TRANSCRIPT.json OUT_CUTS.json [--plan PLAN.json] [--target 30-45]

Without a plan, every sentence is a candidate: fillers, false starts ("I I", "the the") and
pauses longer than maxGap are cut, a sentence that restarts an earlier one is a retake (the last
take is kept), then whole sentences are dropped from the weakest end until the cut fits the
target length. With a plan (written by Claude after reading the transcript):

  {"maxGap": 0.35, "pad": [0.06, 0.10], "target": [30, 45],
   "fix": {"both users": "Mudex"},                       # caption corrections, phrase -> text
   "segments": [{"id": "hook", "role": "hook", "phrase": "these events can't happen ...",
                 "near": 41, "clip": "C6805.MP4", "drop": ["you know"], "focus": 0.49}]}

`focus` is where the 9:16 crop centres (0..1 across the source frame), so a multi-person shot
can be cropped per speaker. OUT: {"duration", "cuts": [{clip, in, out, reason}],
"removed": [{clip, in, out, reason, text}], "takes": [{seg, role, clip, in, out, at, dur, focus, words}]}.
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STYLE = json.loads((ROOT / "style.json").read_text())
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())

ap = argparse.ArgumentParser()
ap.add_argument("transcript"); ap.add_argument("out"); ap.add_argument("--plan"); ap.add_argument("--target")
a = ap.parse_args()
tr = json.load(open(a.transcript))
plan = json.load(open(a.plan)) if a.plan and pathlib.Path(a.plan).exists() else {}
speech = {c["file"] for c in tr["clips"] if not c.get("broll")}
W = [w for w in tr["words"] if w["clip"] in speech]
for i, w in enumerate(W):
    w["i"] = i
max_gap = plan.get("maxGap", 0.35)
pad_in, pad_out = plan.get("pad", [0.06, 0.10])
target = plan.get("target") or ([float(x) for x in a.target.split("-")] if a.target else [30, 45])
fillers = [[norm(x) for x in f.split()] for f in STYLE["cuts"]["fillerWords"] if f not in ("like", "basically", "literally", "so yeah", "kind of", "sort of")]
removed = []


def text(ws):
    return " ".join(w["word"] for w in ws)


def clean(ws, drops=()):
    """Remove fillers, stutters/false starts and planned drops; log each removal."""
    seqs = [(f, "filler") for f in fillers] + [([norm(x) for x in d.split()], "dropped phrase") for d in drops]
    keep, i = [], 0
    while i < len(ws):
        hit = next(((s, r) for s, r in seqs if [norm(w["word"]) for w in ws[i:i + len(s)]] == s), None)
        if hit:
            n = len(hit[0])
            removed.append({"clip": ws[i]["clip"], "in": ws[i]["start"], "out": ws[i + n - 1]["end"], "reason": hit[1], "text": text(ws[i:i + n])})
            i += n; continue
        # false start: the same 1-2 words said twice in a row ("we we", "it's it's", "from the from the")
        for n in (2, 1):
            if i + 2 * n <= len(ws) and [norm(w["word"]) for w in ws[i:i + n]] == [norm(w["word"]) for w in ws[i + n:i + 2 * n]]:
                removed.append({"clip": ws[i]["clip"], "in": ws[i]["start"], "out": ws[i + n - 1]["end"], "reason": "false start", "text": text(ws[i:i + n])})
                i += n; break
        else:
            keep.append(ws[i]); i += 1
    return keep


def find(phrase, near, clip=None):
    p = [norm(x) for x in phrase.split()]
    pool = [w for w in W if clip is None or w["clip"] == clip]
    best = None
    for k in range(len(pool) - len(p) + 1):
        if all(norm(pool[k + j]["word"]) == p[j] for j in range(len(p))):
            d = abs(pool[k]["start"] - near)
            if best is None or d < best[0]:
                best = (d, k)
    if best is None:
        sys.exit(f"phrase not found in transcript: {phrase!r}")
    return pool[best[1]:best[1] + len(p)]


def sentences():
    out, cur = [], []
    for w in W:
        if cur and (w["clip"] != cur[-1]["clip"] or w["start"] - cur[-1]["end"] > 1.2):
            out.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.!?]$", w["word"]):
            out.append(cur); cur = []
    return out + ([cur] if cur else [])


if plan.get("segments"):
    segs = [(s, clean(find(s["phrase"], s.get("near", 0), s.get("clip")), s.get("drop", []))) for s in plan["segments"]]
    chosen = {w["i"] for _, ws in segs for w in ws}
    for s in sentences():
        rest = [w for w in s if w["i"] not in chosen]
        if len(rest) == len(s):
            removed.append({"clip": s[0]["clip"], "in": s[0]["start"], "out": s[-1]["end"], "reason": "not chosen", "text": text(s)})
else:
    S = [clean(s) for s in sentences()]
    S = [s for s in S if s]
    # retakes: a sentence whose first 3 words start a later sentence is an earlier take
    keep = []
    for i, s in enumerate(S):
        head = [norm(w["word"]) for w in s[:3]]
        if len(head) == 3 and any([norm(w["word"]) for w in t[:3]] == head for t in S[i + 1:i + 4]):
            removed.append({"clip": s[0]["clip"], "in": s[0]["start"], "out": s[-1]["end"], "reason": "retake (kept the later take)", "text": text(s)})
        else:
            keep.append(s)
    # fit the target: drop the weakest sentences (short, low confidence) until under the max
    dur = lambda ss: sum(x[-1]["end"] - x[0]["start"] + pad_in + pad_out for x in ss)
    score = lambda s: len(s) * sum(w["prob"] for w in s) / len(s)
    while dur(keep) > target[1] and len(keep) > 1:
        weakest = min(keep[1:], key=score)
        removed.append({"clip": weakest[0]["clip"], "in": weakest[0]["start"], "out": weakest[-1]["end"], "reason": "over target length", "text": text(weakest)})
        keep.remove(weakest)
    segs = [({"id": f"s{i}", "role": "hook" if i == 0 else "body", "focus": 0.5}, s) for i, s in enumerate(keep)]

# caption corrections ("both users" -> "Mudex"): first word takes the text, the rest go silent
fix = {tuple(norm(x) for x in k.split()): v for k, v in plan.get("fix", {}).items()}

takes, cursor = [], 0.0
for seg, ws in segs:
    group = [ws[0]]
    for w in ws[1:]:
        if w["start"] - group[-1]["end"] > max_gap or w["i"] != group[-1]["i"] + 1:
            if w["start"] - group[-1]["end"] > max_gap and w["i"] == group[-1]["i"] + 1:
                removed.append({"clip": w["clip"], "in": group[-1]["end"], "out": w["start"], "reason": f"pause {w['start'] - group[-1]['end']:.2f}s", "text": ""})
            takes.append((seg, group)); group = [w]
        else:
            group.append(w)
    takes.append((seg, group))

res, cuts = [], []
for seg, g in takes:
    t_in, t_out = max(0, g[0]["start"] - pad_in), g[-1]["end"] + pad_out
    words, k = [], 0
    while k < len(g):
        hit = next((key for key in fix if tuple(norm(x["word"]) for x in g[k:k + len(key)]) == key), None)
        if hit:
            words.append({"w": fix[hit], "t0": round(cursor + g[k]["start"] - t_in, 3), "t1": round(cursor + g[k + len(hit) - 1]["end"] - t_in, 3), "prob": 1.0})
            k += len(hit); continue
        x = g[k]
        words.append({"w": x["word"], "t0": round(cursor + x["start"] - t_in, 3), "t1": round(cursor + x["end"] - t_in, 3), "prob": x["prob"]})
        k += 1
    res.append({"seg": seg["id"], "role": seg.get("role", "body"), "clip": g[0]["clip"], "in": round(t_in, 3), "out": round(t_out, 3),
                "at": round(cursor, 3), "dur": round(t_out - t_in, 3), "focus": seg.get("focus", 0.5), "words": words})
    cuts.append({"clip": g[0]["clip"], "in": round(t_in, 3), "out": round(t_out, 3), "reason": f"{seg['id']}: {text(g)}"})
    cursor += t_out - t_in

json.dump({"duration": round(cursor, 3), "target": target, "cuts": cuts, "removed": sorted(removed, key=lambda r: (r["clip"], r["in"])), "takes": res},
          open(a.out, "w"), indent=1)
print(f"{len(res)} takes, {cursor:.2f}s (target {target[0]:g}-{target[1]:g}s)")
for t in res:
    print(f"  {t['at']:6.2f} {t['seg']:<8} {t['dur']:5.2f}s  {' '.join(w['w'] for w in t['words'])}")
if not target[0] <= cursor <= target[1]:
    print(f"WARNING: {cursor:.1f}s is outside the target", file=sys.stderr)
