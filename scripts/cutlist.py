#!/usr/bin/env python3
"""Turn chosen lines into a word-accurate cut list.

Usage: cutlist.py TRANSCRIPT.json PLAN.json OUT.json
PLAN: {"filler": [...], "maxGap": 0.28, "pad": [0.06, 0.10],
       "segments": [{"id": "hook", "phrase": "the moon is the way to get to Mars",
                     "near": 92, "drop": ["of course"], "role": "hook"|"body"}, ...]}
Each phrase is matched word-for-word (case/punctuation-insensitive) in the transcript near
`near` seconds. Within a phrase, dropped words and fillers are removed and any pause longer
than maxGap becomes a jump cut. OUT lists takes [{seg, in, out, words:[{w,t0,t1}]}] in
source time plus the output timeline (each word's time in the cut).
"""
import json, re, sys

norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())

tr, plan, out = (json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3])
W = tr["words"]
fill = [f.split() for f in plan.get("filler", [])]
max_gap, (pad_in, pad_out) = plan.get("maxGap", 0.28), plan.get("pad", [0.06, 0.10])


def find(phrase, near):
    p = [norm(x) for x in phrase.split()]
    best = None
    for i in range(len(W) - len(p) + 1):
        if all(norm(W[i + k]["word"]) == p[k] for k in range(len(p))):
            d = abs(W[i]["start"] - near)
            if best is None or d < best[0]:
                best = (d, i)
    if best is None:
        sys.exit(f"phrase not found: {phrase!r}")
    return best[1], best[1] + len(p)


def strip(words, drops):
    keep, i = [], 0
    seqs = [[norm(x) for x in d.split()] for d in drops] + [[norm(x) for x in f] for f in fill]
    while i < len(words):
        hit = next((s for s in seqs if [norm(w["word"]) for w in words[i:i + len(s)]] == s), None)
        if hit:
            i += len(hit); continue
        keep.append(words[i]); i += 1
    return keep


takes, cursor, timeline = [], 0.0, []
for seg in plan["segments"]:
    a, b = find(seg["phrase"], seg.get("near", 0))
    words = strip(W[a:b], seg.get("drop", []))
    group = [words[0]]
    for w in words[1:]:
        if w["start"] - group[-1]["end"] > max_gap or W.index(w) != W.index(group[-1]) + 1:
            takes.append((seg, group)); group = [w]
        else:
            group.append(w)
    takes.append((seg, group))

res = []
for seg, g in takes:
    t_in, t_out = max(0, g[0]["start"] - pad_in), g[-1]["end"] + pad_out
    words = [{"w": w["word"], "t0": round(cursor + (w["start"] - t_in), 3), "t1": round(cursor + (w["end"] - t_in), 3)} for w in g]
    res.append({"seg": seg["id"], "role": seg.get("role", "body"), "in": round(t_in, 3), "out": round(t_out, 3),
                "at": round(cursor, 3), "dur": round(t_out - t_in, 3), "words": words})
    cursor += t_out - t_in
json.dump({"duration": round(cursor, 3), "takes": res}, open(out, "w"), indent=1)
print(f"{len(res)} takes, {cursor:.2f}s")
for t in res:
    print(f"  {t['at']:6.2f} {t['seg']:<10} {t['dur']:5.2f}s  {' '.join(w['w'] for w in t['words'])}")
