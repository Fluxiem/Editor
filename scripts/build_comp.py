#!/usr/bin/env python3
"""Build the HyperFrames project for one format on top of the assembled A-roll.

Usage: build_comp.py JOB_DIR --format 9x16|16x9|4x5|1x1

Reads JOB_DIR/cuts.json + JOB_DIR/edit.json + style.json and writes JOB_DIR/<format>/:
index.html, compositions/components/caption-highlight.html (this edit's words), assets/
(fonts, sfx; aroll.mp4 and cutout.webm are put there by edit.sh). The folder opens as-is in
HyperFrames Studio (`npx hyperframes preview`).

Blocks used (from the restyled catalog in templates/ovs-vertical): caption-highlight for
captions, focus-blur-resolve for the hook, caption-parallax-layers for the word or logo
behind the subjects, flash-through-white's two-frame flash for transitions.

edit.json: hookText, hookKeys[], keys[] (caption words in the accent block), punch[] / settle[]
(take ids or "take@word"), hero {word | logo, seg, colour}, broll [{src, at, dur}],
cards [{seg} | {from, to, text?}] (text cutaways; captions skip them), transition {look: "cut"|"flash"}
or transitions [{look, where, frames, strength, sound, landsMs, level}], sfx (bool), tail (s).
style.json -> studio (the OVS Video Editor page) sets caption font/size/case/colours, card style,
B-roll push and the default transitions; edit.json wins where both say something.
"""
import argparse, html, json, pathlib, re, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates/ovs-vertical"
STYLE = json.loads((ROOT / "style.json").read_text())
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())

# per-format layout, in output pixels: caption line centre/size, safe x-margin, hook box, hero centre
LAYOUT = {
    "9x16": dict(W=1080, H=1920, capY=STYLE["captions"]["centerY"], cap=STYLE["captions"]["sizePx"], mx=STYLE["safeZone"]["xMin"], hookY=1160, hook=92, heroY=620),
    "4x5": dict(W=1080, H=1350, capY=1010, cap=70, mx=110, hookY=980, hook=84, heroY=470),
    "1x1": dict(W=1080, H=1080, capY=830, cap=64, mx=100, hookY=800, hook=78, heroY=380),
    "16x9": dict(W=1920, H=1080, capY=880, cap=64, mx=260, hookY=850, hook=84, heroY=330),
}

ap = argparse.ArgumentParser()
ap.add_argument("job"); ap.add_argument("--format", default="9x16", choices=LAYOUT)
a = ap.parse_args()
job = pathlib.Path(a.job)
L = LAYOUT[a.format]; W, H = L["W"], L["H"]
proj = job / a.format
cuts, E = json.load(open(job / "cuts.json")), json.load(open(job / "edit.json"))
takes = cuts["takes"]
last_word = max(w["t1"] for t in takes for w in t["words"])
total = round(min(cuts["duration"], last_word + E.get("tail", 0.3)), 3)
hook_end = round(min(sum(t["dur"] for t in takes if t["role"] == "hook") or 2.0, 3.0), 3)


def at(ref):
    m = re.match(r"^([\w-]+)(?:@([^+-]+))?([+-][\d.]+)?$", ref)
    seg, word, off = m.group(1), m.group(2), float(m.group(3) or 0)
    ts = [t for t in takes if t["seg"] == seg]
    if not ts:
        raise SystemExit(f"no take {seg!r} in cuts.json")
    if word is None:
        return round(ts[0]["at"] + off, 3)
    for t in ts:
        for w in t["words"]:
            if norm(w["w"]) == norm(word):
                return round(w["t0"] + off, 3)
    raise SystemExit(f"no word {word!r} in take {seg!r}")


def seg_end(seg):
    ts = [t for t in takes if t["seg"] == seg]
    return round(ts[-1]["at"] + ts[-1]["dur"], 3)


ST = STYLE.get("studio", {})                       # the saved style from the OVS Video Editor page
SC, SK, SB = ST.get("captions", {}), ST.get("cards", {}), ST.get("broll", {})
if SC and a.format == ST.get("reel", {}).get("size", "9x16"):  # caption geometry is set for the main reel size
    L["cap"], L["capY"] = round(SC.get("size", 4) * H / 100), round(SC.get("y", 62) * H / 100)
CASE = {"upper": "uppercase", "lower": "lowercase", "none": "none"}

# ---------- text cutaways: full-screen cards for lines that land (new scene, new caption) ----------
card_spans = []
for c in E.get("cards", []):
    t0 = at(c.get("from", c.get("seg")))
    t1 = at(c["to"]) if "to" in c else seg_end(c["seg"])
    card_spans.append((t0, round(t1, 3), c))
in_card = lambda t: any(c0 <= t < c1 for c0, c1, _ in card_spans)

# ---------- captions: <=N-word groups, break at punctuation and at every cut; hook words skipped ----------
keys = {norm(k) for k in E.get("keys", [])}
per = int(SC.get("words", 3))
words, groups = [], []
for t in takes:
    if t["role"] == "hook":
        continue
    cur = []
    for w in t["words"]:
        if in_card(w["t0"]):
            continue
        # "hard": the caption is gone by the end of its take or the start of the next cutaway
        hard = min([t["at"] + t["dur"]] + [c0 for c0, _, _ in card_spans if c0 > w["t0"]])
        words.append({"text": w["w"].strip().rstrip(".,;:"), "start": w["t0"], "end": min(w["t1"], t["at"] + t["dur"]), "hard": round(hard, 3), "key": norm(w["w"]) in keys})
        cur.append(len(words) - 1)
        if len(cur) == per or re.search(r"[.,!?]$", w["w"]):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
for g in groups:  # at most one accent word per group
    for i in [i for i in g if words[i]["key"]][1:]:
        words[i]["key"] = False

comp = proj / "compositions/components"; comp.mkdir(parents=True, exist_ok=True)
C = STYLE["captions"]
cap_font, cap_weight = SC.get("font", "Inter"), str(SC.get("weight", "900"))
accent = SC.get("accent", STYLE["colors"]["accent"])
cap = (TEMPLATE / "compositions/components/caption-highlight.html").read_text()
js_words = "[\n" + ",\n".join("          " + json.dumps({"text": w["text"], "start": w["start"], "end": w["end"], "hard": w["hard"], **({"key": True} if w["key"] else {})}) for w in words) + "\n        ]"
cap = re.sub(r"var WORDS = \[.*?\n        \];", lambda _: "var WORDS = " + js_words + ";", cap, count=1, flags=re.S)
cap = re.sub(r"var RAW_GROUPS = \[.*?\n        \];", lambda _: "var RAW_GROUPS = " + json.dumps([[g[0], g[-1]] for g in groups]) + ";", cap, count=1, flags=re.S)
# a caption never runs past its own cut: end each group at the next group's start or its take end
cap = cap.replace("WORDS[RAW_GROUPS[gi + 1][0]].start : 8.0", f"WORDS[RAW_GROUPS[gi + 1][0]].start : {total}")
cap = cap.replace("var gEnd = Math.min(WORDS[we].end + 0.5, nextStart - 0.05);", "var gEnd = Math.min(WORDS[we].end + 0.5, nextStart - 0.05, WORDS[we].hard || 1e9);")
cap = cap.replace('data-duration="8"', f'data-duration="{total}"', 1)
cap = cap.replace("width: 1080px;\n        height: 1920px;", f"width: {W}px;\n        height: {H}px;")
cap = cap.replace('data-width="1080"', f'data-width="{W}"').replace('data-height="1920"', f'data-height="{H}"')
cap = cap.replace('content="width=1080, height=1920"', f'content="width={W}, height={H}"')
cap = cap.replace("top: 1130px;", f"top: {L['capY'] - 60}px;").replace("padding: 0 120px;", f"padding: 0 {L['mx']}px;")
cap = cap.replace("font-size: 76px;", f"font-size: {L['cap']}px;")
cap = cap.replace('fitFontSize(groupText, 76, "900", "Inter", 840)', f'fitFontSize(groupText, {L["cap"]}, "{cap_weight}", "{cap_font}", {W - 2 * L["mx"]})')
cap = cap.replace("--ovs-accent: #FFD400;", f"--ovs-accent: {accent};")
cap = cap.replace('--ovs-font-caption: "Inter",', f'--ovs-font-caption: "{cap_font}",')
if SC:
    stroke = int(SC.get("outline", 2)) * 1.5
    shadow = {"soft": "0 4px 18px rgba(0,0,0,0.45)", "hard": "3px 5px 0 rgba(0,0,0,0.85)", "none": "none"}[SC.get("shadow", "soft")]
    cap = cap.replace("font-weight: 900;\n        font-size", f"font-weight: {cap_weight};\n        font-size")
    cap = cap.replace("text-transform: uppercase;", f"text-transform: {CASE[SC.get('case', 'upper')]};")
    cap = cap.replace("color: #ffffff;", f"color: {SC.get('color', '#ffffff')};")
    cap = cap.replace("letter-spacing: 0.02em;", f"letter-spacing: {SC.get('spacing', 2) / 100}em;")
    cap = cap.replace("-webkit-text-stroke: 3px rgba(0,0,0,0.85);", f"-webkit-text-stroke: {stroke}px rgba(0,0,0,0.85);")
    cap = cap.replace("text-shadow: 0 4px 18px rgba(0,0,0,0.45);", f"text-shadow: {shadow};")
    if SC.get("case", "upper") != "upper":
        cap = cap.replace("w.text.toUpperCase()", "w.text" + (".toLowerCase()" if SC.get("case") == "lower" else ""))
    if SC.get("keyStyle") == "colour":
        cap = cap.replace(".hl-key .hl-word-text { color: var(--ovs-accent-ink); }", ".hl-key .hl-word-text { color: var(--ovs-accent); } .hl-key .hl-word-bg { display: none; }")
    elif SC.get("keyStyle") == "none":
        cap = cap.replace(".hl-key .hl-word-text { color: var(--ovs-accent-ink); }", ".hl-key .hl-word-bg { display: none; }")
(comp / "caption-highlight.html").write_text(cap)

for sub in ["assets/fonts", "assets/sfx"]:
    shutil.copytree(TEMPLATE / sub, proj / sub, dirs_exist_ok=True)
for f in ["hyperframes.json", "package.json"]:
    shutil.copy(TEMPLATE / f, proj / f)
(proj / "meta.json").write_text(json.dumps({"id": f"{job.name}-{a.format}", "name": f"{job.name} {a.format}"}, indent=2))

# ---------- B-roll: one smooth push across the whole scene (studio: about 1-2 % a second) ----------
push = SB.get("push", 1.5) / 100
broll_html, broll_js, broll_spans = [], [], []
for i, b in enumerate(E.get("broll", [])):
    t0 = at(b["at"]); d = round(min(b.get("dur", SB.get("minShot", 2.5)), total - t0), 3)
    broll_spans.append((t0, round(t0 + d, 3)))
    if b["src"].lower().endswith((".mp4", ".mov", ".webm")):
        broll_html.append(f'      <video id="broll{i}" class="clip broll" src="{b["src"]}" muted playsinline data-media-start="{b.get("from", 0)}" data-start="{t0}" data-duration="{d}" data-track-index="5"></video>')
    else:
        broll_html.append(f'      <img id="broll{i}" class="clip broll" src="{b["src"]}" alt="" data-start="{t0}" data-duration="{d}" data-track-index="5" />')
    broll_js.append(f'tl.fromTo("#broll{i}", {{ scale: 1.0 }}, {{ scale: {round(1 + push * d, 4)}, duration: {d}, ease: "none" }}, {t0});')

# ---------- transitions: edit.json "transition(s)", else the studio's list; hard cut everywhere else ----------
T = E.get("transitions")
if T is None and "transition" in E:  # short form: {"look": "cut" | "flash", "frames", "strength"}
    T = [] if E["transition"].get("look", "cut") == "cut" else [dict(E["transition"], look="flash2", where=E["transition"].get("where", "every"))]
if T is None:
    T = ST.get("transitions", {}).get("list", []) if ST.get("transitions", {}).get("on") else []
cut_points = {
    "every": [t["at"] for t in takes[1:]],
    "speaker": [t["at"] for p, t in zip(takes, takes[1:]) if abs(t.get("focus", .5) - p.get("focus", .5)) > 0.05],
    "broll": [x for s in broll_spans for x in s],
    "cards": [x for c0, c1, _ in card_spans for x in (c0, c1)],
}
flash_js, punch_extra, sfx = [], set(), []
for tr in T:
    times = sorted({round(x, 3) for x in cut_points.get(tr.get("where", "every"), []) if 0 < x < total})
    look = tr.get("look", "flash2")
    for x in times:
        if look in ("flash2", "whiteflash"):
            fd = round(tr.get("frames", 2) / 30 * (3 if look == "whiteflash" else 1), 3)
            flash_js.append(f'tl.fromTo("#flash", {{ opacity: {tr.get("strength", 58) / 100} }}, {{ opacity: 0, duration: {fd}, ease: "none", immediateRender: false }}, {x});')
        elif look == "punch":
            punch_extra.add(x)
    snd = tr.get("sound")
    if snd and times:
        src = next((p for p in [ROOT / "library/Sounds" / snd, ROOT / "library" / snd] if p.exists()), None)
        if src:
            shutil.copy(src, proj / "assets/sfx" / src.name)
            for x in times:
                sfx.append((src.name, x - tr.get("landsMs", 0) / 1000, round(10 ** (tr.get("level", -12) / 20), 3)))
        else:
            print(f"warning: transition sound {snd!r} not in library/Sounds (Drive: OVS Claude Edit/Library/Sounds)")
    if look in ("whip", "zoomblur"):
        print(f"note: {look} transitions are mounted by hand from the catalog (whip-pan-cut / cinematic-zoom)")
flash_js = (['tl.set("#flash", { opacity: 0 }, 0);'] if flash_js else []) + flash_js
flash_html = f'      <div id="flash" class="clip" data-start="0" data-duration="{total}" data-track-index="20"></div>' if flash_js else ""

# ---------- camera: slow push across each take, punch-ins / settles on chosen cuts ----------
punch = {at(p) for p in E.get("punch", [])} | punch_extra
settle = {at(p) for p in E.get("settle", [])}
P, S, Z = STYLE["cuts"]["punchIn"], STYLE["cuts"]["scaleOutSettle"], STYLE["cuts"]["talkingHead"]["slowZoom"]
cam = []
whoosh = E.get("sfx", ST.get("audio", {}).get("whoosh", True))
bounds = sorted({round(t["at"], 3) for t in takes} | punch | settle)
for i, t0 in enumerate(bounds):
    t1 = bounds[i + 1] if i + 1 < len(bounds) else total
    d = max(0.05, t1 - t0)
    if t0 in punch:
        cam.append(f'tl.fromTo("#cam", {{ scale: {P["from"]} }}, {{ scale: {P["to"]}, duration: {P["durationSec"]}, ease: "{P["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: {P["to"]} }}, {{ immediateRender: false, scale: {round(P["to"] * 1.03, 3)}, duration: {max(0.05, d - P["durationSec"]):.3f}, ease: "none" }}, {t0 + P["durationSec"]:.3f});')
        whoosh and sfx.append(("whoosh.wav", t0 - 0.12, 0.3))
    elif t0 in settle:
        cam.append(f'tl.fromTo("#cam", {{ scale: {S["from"]} }}, {{ scale: {S["to"]}, duration: {S["durationSec"]}, ease: "{S["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: 1 }}, {{ immediateRender: false, scale: 1.04, duration: {max(0.05, d - S["durationSec"]):.3f}, ease: "none" }}, {t0 + S["durationSec"]:.3f});')
        whoosh and sfx.append(("whoosh.wav", t0 - 0.12, 0.3))
    else:
        cam.append(f'tl.fromTo("#cam", {{ scale: {Z["from"]} }}, {{ scale: {Z["to"]}, duration: {d:.3f}, ease: "none" }}, {t0});')

# ---------- text cards: the line plays a few words at a time on a flat colour (A/B alternate) ----------
card_html, card_js = [], []
pal = [(SK.get("bgA", "#EFEAE0"), SK.get("inkA", "#0D0E0C")), (SK.get("bgB", "#303423"), SK.get("inkB", "#EFEAE0"))]
card_font = cap_font if SK.get("font", "same") == "same" else SK["font"]
for ci, (c0, c1, c) in enumerate(card_spans):
    bg, ink = pal[0] if SK.get("bg", "alternate") == "flat" else pal[ci % 2]
    ws = [w for t in takes for w in t["words"] if c0 <= w["t0"] < c1]
    n = int(SK.get("words", 2)) if SK.get("shows", "line") == "line" else 99
    grp = [ws[i:i + n] for i in range(0, len(ws), n)] if not c.get("text") else [[{"w": c["text"], "t0": c0}]]
    spans = []
    for gi, g in enumerate(grp):
        txt = " ".join(w["w"] for w in g)
        if SK.get("punct", "hide") == "hide":
            txt = re.sub(r"[.,!?;:]", "", txt)
        spans.append(f'<span id="card{ci}g{gi}" class="cardline">{html.escape(txt)}</span>')
        g1 = grp[gi + 1][0]["t0"] if gi + 1 < len(grp) else c1
        card_js.append(f'tl.set("#card{ci}g{gi}", {{ visibility: "visible" }}, {g[0]["t0"]}); tl.set("#card{ci}g{gi}", {{ visibility: "hidden" }}, {round(g1, 3)});')
    fs = round(SK.get("size", 5.4) * H / 100)
    card_html.append(f'      <div id="card{ci}" class="clip card" data-start="{c0}" data-duration="{round(c1 - c0, 3)}" data-track-index="8" '
                     f'style="background: {bg}; color: {ink}; font: {SK.get("weight", 800)} {fs}px/1.04 &quot;{card_font}&quot;, sans-serif; letter-spacing: {SK.get("spacing", -5.5) / 100}em; '
                     f'text-transform: {CASE[SK.get("case", "lower")]}; text-align: {SK.get("align", "center")}">{"".join(spans)}</div>')

# ---------- word or logo behind the subjects (caption-parallax-layers recipe), once per video ----------
hero_html, hero_js = "", ""
h = E.get("hero")
if h:
    t0, t1 = at(h["seg"]), seg_end(h["seg"])
    I, D = STYLE["textBehindSubject"]["in"], STYLE["textBehindSubject"]["drift"]
    if h.get("logo"):
        inner = f'<img id="heroWord" src="{h["logo"]}" alt="" style="width: {round(W * 0.8)}px" />'
    else:
        from PIL import ImageFont
        f = ImageFont.truetype(str(TEMPLATE / "assets/fonts/Archivo-Variable.ttf"), 200)
        want = {b"Weight": STYLE["fonts"]["heading"]["weight"], b"Width": STYLE["fonts"]["heading"]["width"]}
        f.set_variation_by_axes([want.get(ax["name"], ax["default"]) for ax in f.get_variation_axes()])
        l, _, r, _ = f.getbbox(h["word"].upper())
        px = round(200 * W * STYLE["textBehindSubject"]["fitWidthPct"] / 100 / (r - l), 1)
        inner = f'<span id="heroWord" style="font-size: {px}px">{html.escape(h["word"].upper())}</span>'
    hero_html = (f'        <div id="hero" class="clip" data-start="{t0}" data-duration="{round(t1 - t0, 3)}" data-track-index="2">{inner}</div>\n'
                 f'        <video id="cutout" class="clip" src="assets/cutout.webm" data-start="{t0}" data-media-start="0" data-duration="{round(t1 - t0, 3)}" data-track-index="3" muted playsinline data-layout-allow-occlusion></video>')
    hero_js = (f'tl.fromTo("#heroWord", {{ scale: {I["scaleFrom"]}, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: {I["durationSec"]}, ease: "{I["ease"]}" }}, {t0});\n'
               f'      tl.fromTo("#heroWord", {{ scale: 1 }}, {{ immediateRender: false, scale: {1 + D["scale"]}, duration: {round(t1 - t0 - I["durationSec"], 3)}, ease: "none" }}, {round(t0 + I["durationSec"], 3)});')
    (proj / "cutout.json").write_text(json.dumps({"start": t0, "end": t1}))  # edit.sh makes assets/cutout.webm for this span

if E.get("sfx", ST.get("audio", {}).get("pop", True)):
    last = -9
    for w in words:
        if w["key"] and w["start"] - last >= 1.5:
            sfx.append(("pop.wav", w["start"], 0.28)); last = w["start"]
sfx_html = "\n".join(f'      <audio id="sfx{i}" class="clip" src="assets/sfx/{n}" data-start="{max(0, round(t, 3))}" data-duration="{0.5 if n in ("pop.wav", "whoosh.wav") else 1.5}" data-volume="{v}" data-track-index="{30 + i % 8}"></audio>'
                     for i, (n, t, v) in enumerate(sorted(sfx, key=lambda x: x[1])))

# ---------- hook: focus-blur-resolve, the first spoken line on screen from frame 1 ----------
HK = STYLE["hook"]["text"]
hk = {norm(k) for k in E.get("hookKeys", [])}
hook_words = "".join(f'<span class="{"key" if norm(w) in hk else ""}">{html.escape(w)}</span>' for w in E["hookText"].upper().split())
heroc = (h or {}).get("colour", STYLE["colors"]["accent"])

index = f"""<!doctype html>
<html lang="en" data-resolution="{'portrait' if H > W else 'landscape'}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Archivo"; src: url("assets/fonts/Archivo-Variable.ttf") format("truetype"); font-weight: 100 900; font-stretch: 62% 125%; font-display: block; }}
      :root {{ --accent: {STYLE["colors"]["accent"]}; --accent-ink: {STYLE["colors"]["accentInk"]}; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #bg {{ position: absolute; inset: 0; background: #000; }}
      #cam {{ position: absolute; inset: 0; transform-origin: 50% 35%; overflow: hidden; }}
      #aroll, #cutout {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      #cutout {{ z-index: 3; }}
      #hero {{ position: absolute; left: 0; right: 0; top: {L["heroY"] - 260}px; height: 520px; display: flex; align-items: center; justify-content: center; z-index: 2; }}
      #heroWord {{ display: inline-block; font-family: "Archivo", "Arial Black", sans-serif; font-weight: 900; font-stretch: {STYLE["fonts"]["heading"]["width"]}%; color: {heroc}; line-height: 1; white-space: nowrap; transform-origin: 50% 50%; }}
      #captions {{ z-index: 10; }}
      .broll {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 5; }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; z-index: 20; }}
      .card {{ position: absolute; inset: 0; z-index: 9; display: flex; align-items: center; justify-content: center; padding: 0 {L["mx"]}px; }}
      .cardline {{ position: absolute; left: {L["mx"]}px; right: {L["mx"]}px; visibility: hidden; }}
      #hook {{ position: absolute; left: {L["mx"]}px; right: {L["mx"]}px; top: {L["hookY"] - 150}px; height: 300px; display: flex; align-items: center; justify-content: center; z-index: 12; }}
      .hf-catalog-focus-blur-resolve {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 4px 18px; max-width: {W - 2 * L["mx"]}px; text-align: center; color: #fff; font: 900 {L["hook"]}px/1.02 "Inter", sans-serif; letter-spacing: -0.02em; transform-origin: 50% 50%; -webkit-text-stroke: {C["strokePx"]}px {C["strokeColor"]}; paint-order: stroke fill; text-shadow: {C["shadow"]}; }}
      .hf-catalog-focus-blur-resolve span {{ display: inline-block; filter: blur(calc(var(--hf-word-blur, 0px))); }}
      .hf-catalog-focus-blur-resolve span.key {{ background: var(--accent); color: var(--accent-ink); -webkit-text-stroke: 0; text-shadow: none; border-radius: 10px; padding: 0 14px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
      <div id="bg" class="clip" data-start="0" data-duration="{total}" data-track-index="0"></div>
      <div id="cam">
        <video id="aroll" class="clip" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{total}" data-has-audio="true" data-track-index="1" playsinline></video>
{hero_html}
      </div>
{chr(10).join(broll_html)}
{chr(10).join(card_html)}
      <div id="captions" data-composition-src="compositions/components/caption-highlight.html" data-composition-id="caption-highlight" data-start="0" data-duration="{total}" data-track-index="10"></div>
      <div id="hook" class="clip" data-start="0" data-duration="{hook_end}" data-track-index="13"><div class="hf-catalog-focus-blur-resolve">{hook_words}</div></div>
{flash_html}
{sfx_html}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      tl.set("#cam", {{ scale: 1 }}, 0);
      {(chr(10) + '      ').join(cam)}
      tl.fromTo(".hf-catalog-focus-blur-resolve span", {{ opacity: {HK["from"]["opacity"]}, "--hf-word-blur": "{HK["from"]["blurPx"]}px" }}, {{ opacity: 1, "--hf-word-blur": "0px", duration: {HK["durationSec"]}, ease: "{HK["ease"]}" }}, 0);
      tl.fromTo(".hf-catalog-focus-blur-resolve", {{ scale: {HK["from"]["scale"]} }}, {{ scale: 1, duration: {HK["durationSec"]}, ease: "{HK["ease"]}" }}, 0);
      {(chr(10) + '      ').join(broll_js)}
      {(chr(10) + '      ').join(flash_js)}
      {(chr(10) + '      ').join(card_js)}
      {hero_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
(proj / "index.html").write_text(index)
print(f"{proj / 'index.html'}  {W}x{H}, {total}s, {len(groups)} caption groups, {sum(w['key'] for w in words)} key words, {len(sfx)} sfx")
