#!/usr/bin/env python3
"""Build the HyperFrames project for one format on top of the assembled A-roll.

Usage: build_comp.py JOB_DIR --format 9x16|16x9|4x5|1x1 [--music-args]

Reads JOB_DIR/cuts.json + JOB_DIR/edit.json + style.json and writes JOB_DIR/<format>/:
index.html, compositions/components/caption-highlight.html (this edit's words), cutout.json
({"spans": [{start, end, file}]}: the stretches edit.sh cuts the people out for), assets/ (fonts,
sfx, logos, transitions; aroll.mp4, cutout_<i>.webm and music.m4a are put there by edit.sh). The
folder opens as-is in HyperFrames Studio (`npx hyperframes preview`). With --music-args it only
prints the scripts/music.py arguments for this job's music bed (nothing when there is none) and
writes nothing: edit.sh step e runs that first, so the bed exists when the build mounts it.

Blocks used (from the restyled catalog in templates/ovs-vertical): caption-highlight for
captions, focus-blur-resolve for the hook, caption-parallax-layers for the word or logo
behind the subjects, flash-through-white's two-frame flash for transitions. The motion-graphic
scenes borrow number-pop-in (stat), spring-pop (list, logo), notes-typing / typed-prompt (typed,
the source year) and lt-color-block (lowerthird).

edit.json: hookText, hookKeys[], keys[] (caption words in the accent block), punch[] / settle[]
(take ids or "take@word"), hero {word | logo, seg, colour}, broll [{src, at, dur}],
cards [{seg} | {from, to, text?}] (text cutaways; captions skip them), transition {look: "cut"|"flash"}
or transitions [{look, where, frames, strength, sound, landsMs, level}], sfx (bool), tail (s), and
  studio       {...}: deep-merged over style.json -> studio for this job only. Naming another look
               ({"look": {"name": "glow"}}, or just "glow") starts from style.json -> looks.<name>.
  scenes       [{id, kind, at: "take@word", dur?, layer: front|behind, pos: top|middle, punch?, ...}]:
               one motion graphic per idea, fired on its trigger word: fast in (motion.inSec, ease-out),
               hold, clean out (motion.outSec) before the next scene starts. Kinds:
                 stat {value, prefix, suffix, label}        the number counts up
                 list {title?, items [{text, at?}]}         tiles / rows pop in on their own words
                 notifications {items [{app, title, body, at?}]}   a stack, newest on top
                 source {title, subtitle, year, label?}     a card, the year types in
                 quote {text}    logo {src} (library/Logos)    typed {text, mode: prompt|notes}
                 lowerthird {name, role}
               Default length: to the end of the trigger's sentence (motion.holdMinSec..4s), longer if
               its items or typing need it, never past the next scene or the end. pos "top" hangs from
               the top of the safe area, "middle" sits just above the caption line (a lowerthird sits
               there, left-aligned, by default). layer "behind" goes between the footage and the people
               cutout (adds a cutout span). Each scene start gets a push-in ("punch": false skips it).
  transitions  [..] look "overlay": {file (library/Transitions), markFrame, blend: screen|normal|lighten,
               strength}: the clip is laid over each cut with its markFrame on the cut; the sidecar
               <file>.json gives markFrame / blend / frames (length). where: every | speaker | broll |
               cards | scenes (scene starts).
  music        {file (library/Music or a path), level, duck, duckDb, start, fadeIn, fadeOut} | "file" |
               false (no music); absent -> studio.audio.track when that is set.
style.json -> studio (the OVS Video Editor page) sets caption font/size/case/colours (keyStyle block |
colour | serif | none; serif = the key word in keyFont italic at keyScale x the caption size, filled
with the look gradient), card style, B-roll push, the default transitions, the look (name house | glow,
bg, glow, gradient, text, muted, labelFont), motion (on, theme, inSec, outSec, holdMinSec, pushMaxPct)
and audio (track, musicLevel, duck, duckDb, fadeIn, fadeOut, musicStart, whoosh, pop, sfxPalette house |
kit: hit on the hook, tap on each list item / notification, whoosh on each scene change, chime at the
end); edit.json wins where both say something. The house look writes what it always has; "glow" is
Soft Glow from the 5-Pass Reel Edit Kit (style.json -> looks.glow): near-black glass, warm glow,
gradient serif-italic key words, mono labels, Instagram's UI bands kept clear, push-ins <= 6 %.
"""
import argparse, html, json, pathlib, re, shlex, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates/ovs-vertical"
STYLE = json.loads((ROOT / "style.json").read_text())
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())
esc = lambda s: html.escape(str(s))

# per-format layout, in output pixels: caption line centre/size, safe x-margin, hook box, hero centre
LAYOUT = {
    "9x16": dict(W=1080, H=1920, capY=STYLE["captions"]["centerY"], cap=STYLE["captions"]["sizePx"], mx=STYLE["safeZone"]["xMin"], hookY=1160, hook=92, heroY=620),
    "4x5": dict(W=1080, H=1350, capY=1010, cap=70, mx=110, hookY=980, hook=84, heroY=470),
    "1x1": dict(W=1080, H=1080, capY=830, cap=64, mx=100, hookY=800, hook=78, heroY=380),
    "16x9": dict(W=1920, H=1080, capY=880, cap=64, mx=260, hookY=850, hook=84, heroY=330),
}
# defaults for the studio keys older saved styles don't have yet
HOUSE_LOOK = {"name": "house", "bg": "#0D0E0C", "glow": "#FFD400", "gradient": ["#FFD400", "#FFD400", "#FFD400"], "text": "#FFFFFF", "muted": "#A9A79E", "labelFont": "JetBrains Mono"}
MOTION = {"on": True, "inSec": 0.3, "outSec": 0.25, "holdMinSec": 1.2, "pushMaxPct": 6}
# families the HyperFrames renderer bundles (resolve by name); anything else needs an @font-face to a file
BUNDLED = {re.sub(r"[^a-z0-9]", "", f.lower()) for f in ["Inter", "Montserrat", "Outfit", "Nunito", "Oswald", "League Gothic", "Archivo Black", "Space Mono", "IBM Plex Mono",
                                                          "JetBrains Mono", "EB Garamond", "Playfair Display", "Source Code Pro", "Noto Sans JP", "Roboto", "Open Sans", "Lato", "Poppins"]}

ap = argparse.ArgumentParser()
ap.add_argument("job"); ap.add_argument("--format", default="9x16", choices=LAYOUT)
ap.add_argument("--music-args", action="store_true", help="print the scripts/music.py arguments for the music bed (nothing if none) and exit")
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


def deep(base, over):
    """over merged into base: dicts key by key, anything else (lists too) replaced."""
    out = dict(base)
    for k, v in over.items():
        out[k] = deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def rgba(hexc, alpha):
    h = hexc.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h[:6]
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


# ---------- the style: the saved style from the OVS Video Editor page, this job's edit.json "studio" on top ----------
ST = STYLE.get("studio", {})
JS = E.get("studio") or {}
if isinstance(JS, str):  # "glow": one of style.json -> looks
    JS = {"look": {"name": JS}}
want = JS.get("look", {}).get("name")
if want and want != ST.get("look", {}).get("name", "house"):  # another look for this one video: start from its preset
    ST = deep(ST, STYLE.get("looks", {}).get(want, {}))
ST = deep(ST, JS)
SC, SK, SB = ST.get("captions", {}), ST.get("cards", {}), ST.get("broll", {})
AU, MO = ST.get("audio", {}), dict(MOTION, **ST.get("motion", {}))
LOOK = dict(HOUSE_LOOK, **ST.get("look", {}))
GLOW = LOOK["name"] == "glow"                       # captions, cards, hook and hero word in the Soft Glow look
THEME = MO.get("theme") or LOOK["name"]             # the motion-graphic scenes' look
GRAD = f"linear-gradient(100deg, {LOOK['gradient'][0]} 0%, {LOOK['gradient'][1]} 50%, {LOOK['gradient'][-1]} 100%)"
KEY_FONT, KEY_SCALE, SERIF = SC.get("keyFont", "Instrument Serif"), float(SC.get("keyScale", 1.7)), SC.get("keyStyle") == "serif"


def music_plan():
    """This job's music bed: edit.json "music" (false = none), else studio.audio.track; None when there is none."""
    m = E.get("music")
    if m is False:
        return None
    m = {"file": m} if isinstance(m, str) else (m or {})
    name = m.get("file") or AU.get("track") or ""
    if not name:
        return None
    src = next((p for p in [ROOT / "library/Music" / name, job / name, ROOT / name, pathlib.Path(name)] if p.is_file()), None)
    if src is None:
        print(f"warning: music {name!r} not in library/Music (Drive: OVS Claude Edit/Library/Music); going without music", file=sys.stderr)
        return None
    return {"file": src, "level": m.get("level", AU.get("musicLevel", -20)), "duck": m.get("duck", AU.get("duck", True)),
            "duckDb": m.get("duckDb", AU.get("duckDb", 8)), "start": m.get("start", AU.get("musicStart", 0)),
            "fadeIn": m.get("fadeIn", AU.get("fadeIn", 0.5)), "fadeOut": m.get("fadeOut", AU.get("fadeOut", 1.5))}


if a.music_args:  # edit.sh step e: scripts/music.py makes assets/music.m4a before the build mounts it
    mu = music_plan()
    if mu:
        A = proj / "assets"
        print(shlex.join([str(mu["file"]), str(A / "aroll.mp4"), str(A / "music.m4a"), "--duration", str(total), "--level", str(mu["level"]),
                          "--start", str(mu["start"]), "--fade-in", str(mu["fadeIn"]), "--fade-out", str(mu["fadeOut"])]
                         + (["--duck", str(mu["duckDb"])] if mu["duck"] else ["--no-duck"])))
    raise SystemExit(0)


def font_files(family):
    """Font files named like family (InstrumentSerif-Italic.ttf for "Instrument Serif") in the template or library/Fonts."""
    key = re.sub(r"[^a-z0-9]", "", family.lower())
    for d in [TEMPLATE / "assets/fonts", ROOT / "library/Fonts"]:
        fs = [f for f in sorted(d.glob("*")) if d.is_dir() and f.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2")
              and re.sub(r"[^a-z0-9]", "", f.stem.lower()).startswith(key)]
        if fs:
            return fs
    return []


def font_faces(family):
    """@font-face rules (one line each) for a family the renderer doesn't bundle, its files copied into assets/fonts."""
    if re.sub(r"[^a-z0-9]", "", family.lower()) in BUNDLED:
        return []
    fs = font_files(family)
    if not fs:
        print(f"warning: font {family!r} is not bundled and has no file in Library/Fonts; the render falls back to another face")
    (proj / "assets/fonts").mkdir(parents=True, exist_ok=True)
    rules = []
    for f in fs:
        shutil.copy(f, proj / "assets/fonts" / f.name)
        s = f.stem.lower()
        weight = next((v for k, v in [("thin", 100), ("extralight", 200), ("light", 300), ("medium", 500), ("semibold", 600), ("extrabold", 800), ("bold", 700), ("black", 900)] if k in s),
                      "100 900" if "variable" in s else 400)
        fmt = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}[f.suffix.lower()]
        rules.append(f'@font-face {{ font-family: "{family}"; src: url("assets/fonts/{f.name}") format("{fmt}"); font-style: {"italic" if "italic" in s else "normal"}; font-weight: {weight}; font-display: block; }}')
    return rules


SERIF_TTF = next((f for f in font_files(KEY_FONT) if "italic" in f.stem.lower()), None) or next(iter(font_files(KEY_FONT)), None)


def text_px(text, font_file, width, size=200, axes=None, pad=0.0):
    """Font size (px) at which text sets one line `width` wide in this font file (pad: extra width in em)."""
    from PIL import ImageFont
    f = ImageFont.truetype(str(font_file), size)
    if axes:
        f.set_variation_by_axes([axes.get(ax["name"], ax["default"]) for ax in f.get_variation_axes()])
    l, _, r, _ = f.getbbox(text)
    return round(width / (max(r - l, 1) / size + pad), 1)


def fit_px(text, width, cap, serif=False, heading=False):
    """One-line font size for text in `width`, at most cap: measured in the serif or heading face, else Inter Black estimated."""
    text = text or " "
    if serif and SERIF_TTF:
        return min(cap, text_px(text, SERIF_TTF, width, pad=0.2))
    if serif:
        return min(cap, round(width / (0.42 * len(text) + 0.2), 1))
    if heading:
        want = {b"Weight": STYLE["fonts"]["heading"]["weight"], b"Width": STYLE["fonts"]["heading"]["width"]}
        return min(cap, text_px(text.upper(), TEMPLATE / "assets/fonts/Archivo-Variable.ttf", width, axes=want))
    return min(cap, round(width / (0.7 * len(text)), 1))


if SC and a.format == ST.get("reel", {}).get("size", "9x16"):  # caption geometry is set for the main reel size
    L["cap"], L["capY"] = round(SC.get("size", 4) * H / 100), round(SC.get("y", 62) * H / 100)
CASE = {"upper": "uppercase", "lower": "lowercase", "none": "none"}
IG = STYLE["safeZone"]["instagram"] if GLOW and a.format == "9x16" else None
if IG:  # Soft Glow keeps text out of Instagram's UI: top 220, bottom 380, right 140 px
    L["mx"] = max(L["mx"], IG["rightPx"])
    L["capY"] = max(IG["topPx"] + L["cap"], min(L["capY"], H - IG["bottomPx"] - L["cap"]))

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
# no per-word brightness pulse: the renderer draws a filtered, stroked word grey for a frame or two
cap = re.sub(r"\n\s*tl\.to\(\s*wordEl,\s*\{ filter: \"brightness\([\d.]+\)\"[^}]*\},\s*w\.start[^)]*\);", "", cap)
cap = cap.replace("will-change: transform, filter;", "will-change: transform;")
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
if SERIF:  # the key word in the serif italic at keyScale x, look gradient fill, no stroke; support words stay as set above
    txt = {"upper": "x.text.toUpperCase()", "lower": "x.text.toLowerCase()"}.get(SC.get("case", "upper"), "x.text")
    cap = cap.replace("        var GROUPS = RAW_GROUPS.map", f"""        // serif key words: measure each word in its own face so the line still fits the safe width
        function fitKeyed(ws, base, weight, family, maxWidth) {{
          var size = base;
          var minSize = Math.floor(base * 0.45);
          while (size > minSize) {{
            var width = 0;
            ws.forEach(function (x) {{
              var k = Math.round(size * {KEY_SCALE});
              _fitCtx.font = x.key ? "italic 400 " + k + 'px "{KEY_FONT}"' : weight + " " + size + "px " + family;
              width += _fitCtx.measureText({txt}).width + (x.key ? k * 0.2 + 8 : 24) + 8;
            }});
            if (width <= maxWidth) return size;
            size -= 2;
          }}
          return minSize;
        }}

        var GROUPS = RAW_GROUPS.map""", 1)
    cap = cap.replace("var computedSize = fitFontSize(groupText,", "var computedSize = fitKeyed(groupWords,")
    cap = cap.replace('wordEl.style.fontSize = computedSize + "px";', f'wordEl.style.fontSize = (w.key ? Math.round(computedSize * {KEY_SCALE}) : computedSize) + "px";')
    rules = "\n      ".join(font_faces(KEY_FONT) + [
        "#hl-container .hl-group { align-items: baseline; align-content: center; }",
        f'.hl-word.hl-key {{ font-family: "{KEY_FONT}", serif; font-style: italic; font-weight: 400; letter-spacing: 0; padding: 0 4px; -webkit-text-stroke: 0; text-shadow: none; }}',
        ".hl-word.hl-key .hl-word-bg { display: none; }",
        f".hl-word.hl-key .hl-word-text {{ color: transparent; background: {GRAD}; -webkit-background-clip: text; background-clip: text; padding: 0 0.1em; filter: drop-shadow(0 4px 14px rgba(0,0,0,0.45)); }}"])
    cap = cap.replace("  </head>\n", f"    <style>\n      {rules}\n    </style>\n  </head>\n", 1)
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

# ---------- motion-graphic scenes: one idea on screen at a time, each fired on its trigger word ----------
IN, OUT, HOLD = float(MO["inSec"]), float(MO["outSec"]), float(MO["holdMinSec"])
KINDS = ("stat", "list", "notifications", "source", "quote", "logo", "typed", "lowerthird")
KEY_GAPS = [0.1, 0.033, 0.2, 0.133, 0.2, 0.033, 0.067, 0.033, 0.1, 0.067, 0.033, 0.067, 0.067, 0.067, 0.133, 0.067, 0.033, 0.067, 0.1, 0.1]  # notes-typing's keystrokes
take_end = lambda t: next((round(k["at"] + k["dur"], 3) for k in takes if k["at"] <= t < k["at"] + k["dur"]), total)
type_len = lambda s: min(3.0, 0.055 * len(s))
scenes = sorted(({**s, "t0": at(s["at"])} for s in (E.get("scenes", []) if MO.get("on", True) else [])), key=lambda s: s["t0"])
for k, s in enumerate(scenes):
    if s.get("kind") not in KINDS:
        raise SystemExit(f"scene {s.get('id', k)}: kind {s.get('kind')!r} is not one of {', '.join(KINDS)}")
    t0, nxt = s["t0"], scenes[k + 1]["t0"] if k + 1 < len(scenes) else total
    items = s.get("items", []) if s["kind"] in ("list", "notifications") else []
    gap = max(0.25, min(0.8, (s["dur"] - IN - HOLD) / max(1, len(items) - 1))) if "dur" in s else 0.5
    times, prev = [], t0 + IN / 2 - gap
    for it in items:  # each item on its own word, else evenly after the scene comes in
        prev = at(it["at"]) if it.get("at") else prev + gap
        times.append(prev)
    if "dur" in s:
        t1 = t0 + s["dur"]
    else:  # to the end of the trigger's sentence (holdMinSec..4s), longer if its items or its typing need it
        t1 = min(max(take_end(t0), t0 + HOLD), t0 + 4.0)
        t1 = max([t1] + [t + HOLD for t in times] + ([t0 + IN + 0.1 + type_len(s.get("text", "")) + HOLD] if s["kind"] == "typed" else []))
    s["t1"] = round(min(t1, nxt, total), 3)
    s["times"] = [round(min(max(t, t0), s["t1"] - OUT - 0.1), 3) for t in times]
    if s["t1"] - t0 < IN + OUT + 0.3:
        print(f"warning: scene {s.get('id', k)} is on screen {s['t1'] - t0:.2f}s, too short to read: move it or give it a dur")
    if any(c0 < s["t1"] and t0 < c1 for c0, c1, _ in card_spans):
        print(f"note: scene {s.get('id', k)} overlaps a text card, which covers it")

G = THEME == "glow"
BW = W - 2 * L["mx"]                                          # scene width inside the safe margins
STOP = round(STYLE["safeZone"]["yMin"] * H / 1920)            # "top" hangs from here
SBOT = L["capY"] - round(L["cap"] * 1.3)                      # "middle" / lowerthird sit on this line, above the captions
I, D = STYLE["textBehindSubject"]["in"], STYLE["textBehindSubject"]["drift"]


def typing(el, text, start, dur):
    """notes-typing's keystroke rhythm squeezed into dur, driven like typed-prompt (the text grows with the timeline)."""
    raw = [KEY_GAPS[i % len(KEY_GAPS)] for i in range(len(text))]
    k, ts, t = dur / max(sum(raw), 1e-3), [], 0.0
    for g in raw:
        ts.append(round(t, 3)); t += g * k
    return (f'(function () {{ var el = document.getElementById("{el}"), s = el.dataset.text, T = {json.dumps(ts)}, d = {{ t: 0 }}; el.textContent = "";\n'
            f'        tl.to(d, {{ t: {round(dur, 3)}, duration: {round(dur, 3)}, ease: "none", onUpdate: function () {{ var n = 0; while (n < T.length && T[n] < d.t) n++; el.textContent = s.slice(0, n); }} }}, {round(start, 3)}); }})();')


def count(el, value, start, dur):
    """number-pop-in's count: 0 up to value, formatted like it was written (decimals, thousands commas)."""
    dec = len(value.split(".")[1]) if "." in value else 0
    sep = 'p[0] = p[0].replace(/\\B(?=(\\d{3})+(?!\\d))/g, ","); ' if "," in value else ""
    return (f'(function () {{ var el = document.getElementById("{el}"), d = {{ x: 0 }}, f = function (x) {{ var p = x.toFixed({dec}).split("."); {sep}return p.join("."); }}; el.textContent = f(0);\n'
            f'        tl.to(d, {{ x: {float(value.replace(",", ""))}, duration: {dur}, ease: "power2.out", onUpdate: function () {{ el.textContent = f(d.x); }} }}, {start}); }})();')


def blink(sel, t, until):
    """the caret blinks a few times after typing (finite tl.set toggles, never repeat: -1), cut short by the scene's exit."""
    return [f'tl.set("{sel}", {{ opacity: {b % 2} }}, {round(t + 0.35 + b * 0.53, 3)});' for b in range(4) if t + 0.35 + b * 0.53 < until - 0.1]


pop = lambda sel, t, s=0.6: f'tl.fromTo("{sel}", {{ opacity: 0, scale: {s} }}, {{ opacity: 1, scale: 1, duration: 0.32, ease: "back.out(2)" }}, {round(t, 3)});'
scene_front, scene_behind, scene_js, scene_punch, scene_starts, item_times, behind_spans = [], [], [], set(), [], [], []
for i, s in enumerate(scenes):
    kind, t0, t1, sid, js = s["kind"], s["t0"], s["t1"], f"sc{i}", []
    behind = s.get("layer", "front") == "behind"
    pos = s.get("pos") or ("hero" if behind else "lower" if kind == "lowerthird" else "top")
    card = "gcard" if G else "hcard"
    if kind == "stat":
        val, pre, suf, lab = str(s.get("value", "")), s.get("prefix", ""), s.get("suffix", ""), s.get("label", "")
        px = fit_px(pre + val + suf, W * 0.76 if behind else BW - (420 if lab else 110), cap=440 if behind else 170 if G else 150, serif=G, heading=behind and not G)
        sc = "gserif" if G else "hbig" if behind else ""
        num = (f'<div id="{sid}num" class="num{"" if G or behind else " hblock"}" style="font-size: {px}px"><span class="{sc}">{esc(pre)}'
               f'<span id="{sid}n">{esc(val)}</span>{esc(suf)}</span></div>')
        if behind:
            body = num + (f'<div class="{"gsans" if G else "hcap"}" style="font-size: {42 if G else 54}px">{esc(lab)}</div>' if lab else "")
        else:  # a compact row (number, then its label) so it stays above the speaker's head
            lab = f'<div class="{"gsans" if G else "hcap"} slab">{esc(lab)}</div>' if lab else ""
            body = f'<div class="{"gcard " if G else ""}srow">{num}{lab}</div>'
        js.append(f'tl.fromTo("#{sid}num", {{ y: 24, scale: 0.82, filter: "blur(8px)" }}, {{ y: 0, scale: 1, filter: "blur(0px)", duration: 0.34, ease: "back.out(1.8)" }}, {t0});')
        counts = re.fullmatch(r"\d[\d,]*(\.\d+)?", val) and float(val.replace(",", "")) >= 10 and suf.lower() not in ("st", "nd", "rd", "th")
        if s.get("count", counts):  # small numbers and ordinals ("2nd") just land; counting them reads as "1nd"
            js.append(count(f"{sid}n", val, round(t0 + 0.08, 3), round(min(0.9, max(0.3, (t1 - t0) * 0.4)), 3)))
    elif kind == "list":
        texts = [str(it.get("text", "")) for it in s.get("items", [])]
        tiles = 0 < len(texts) <= 4 and max(map(len, texts)) <= 12   # short items: app tiles, tapped one by one
        head = (f'<div class="glabel">{esc(s["title"])}</div>' if G else f'<div class="hcap" style="font-size: 50px">{esc(s["title"])}</div>') if s.get("title") else ""
        if tiles:
            cols = len(texts) if len(texts) <= 3 else 2
            tw = round(min(180 if G else 260, (BW - (cols - 1) * 28) / cols))   # glow: square app icons; house: yellow blocks
            cells = [(f'<div id="{sid}t{k}" class="tile"><div class="gicon" style="width: {tw}px; height: {tw}px"><span class="gserif" style="font-size: {round(tw * 0.5)}px">{esc(t[:1].upper())}</span>'
                      f'<i id="{sid}r{k}" class="gring"></i></div><div class="glabel">{esc(t)}</div></div>') if G else
                     f'<div id="{sid}t{k}" class="hblock htile" style="width: {tw}px; height: {round(tw * 0.5)}px; font-size: {fit_px(t, tw - 28, cap=50)}px">{esc(t)}</div>'
                     for k, t in enumerate(texts)]
            body = head + f'<div class="tiles" style="grid-template-columns: repeat({cols}, {tw}px)">{"".join(cells)}</div>'
        else:
            rows = [f'<div id="{sid}t{k}" class="gcard grow"><span class="glabel">{k + 1:02d}</span><span class="gsans">{esc(t)}</span></div>' if G else
                    f'<div id="{sid}t{k}" class="hblock hrow"><span class="hidx">{k + 1}</span>{esc(t)}</div>' for k, t in enumerate(texts)]
            body = head + f'<div class="rows">{"".join(rows)}</div>'
        for k, t in enumerate(s["times"]):
            js.append(pop(f"#{sid}t{k}", t))
            if G and tiles:
                js.append(f'tl.fromTo("#{sid}r{k}", {{ opacity: 0.95, scale: 1 }}, {{ opacity: 0, scale: 1.16, duration: 0.5, ease: "power2.out", immediateRender: false }}, {round(t + 0.1, 3)});')
        item_times += s["times"]
    elif kind == "notifications":
        its, step, show = s.get("items", []), 172, 3   # card + gap, cards kept on screen
        cards = [f'<div id="{sid}n{k}" class="note {card}"><div class="nicon">{esc(str(it.get("app", "")).strip()[:1].upper() or "+")}</div><div class="ntext">'
                 f'<div class="nhead"><span>{esc(it.get("app", ""))}</span><span>now</span></div><div class="ntitle">{esc(it.get("title", ""))}</div>'
                 f'<div class="nbody">{esc(it.get("body", ""))}</div></div></div>' for k, it in enumerate(its)]
        body = f'<div class="stack" style="height: {min(len(its), show) * step - 18}px">{"".join(cards)}</div>'
        for k, t in enumerate(s["times"]):  # newest on top: it drops in, the older ones slide down a slot, past `show` they go
            js.append(f'tl.fromTo("#{sid}n{k}", {{ opacity: 0, y: -50, scale: 0.94 }}, {{ opacity: 1, y: 0, scale: 1, duration: 0.32, ease: "power3.out" }}, {t});')
            for j in range(k):
                js.append(f'tl.fromTo("#{sid}n{j}", {{ y: {(k - j - 1) * step} }}, {{ y: {(k - j) * step}, duration: 0.3, ease: "power3.out", immediateRender: false }}, {t});')
                if k - j == show:
                    js.append(f'tl.fromTo("#{sid}n{j}", {{ opacity: 1 }}, {{ opacity: 0, duration: 0.2, ease: "power2.in", immediateRender: false }}, {t});')
        item_times += s["times"]
    elif kind == "source":
        yr, sub = str(s.get("year", "")), s.get("subtitle", "")
        typed = f'<div class="yr"><span id="{sid}ty" class="{"gserif" if G else ""}" data-text="{esc(yr)}">{esc(yr)}</span><i id="{sid}c" class="caret"></i></div>' if yr else ""
        if G:
            body = (f'<div class="gcard src"><div class="scol"><div class="glabel">{esc(s.get("label", "Source"))}</div><div class="gsans stitle">{esc(s.get("title", ""))}</div>'
                    + (f'<div class="glabel">{esc(sub)}</div>' if sub else "") + '</div>' + typed + '</div>')
        else:
            body = (f'<div class="hcard src"><div class="scol"><div class="hpill">{esc(s.get("label", "Source"))}</div><div class="stitle">{esc(s.get("title", ""))}</div>'
                    + (f'<div class="ssub">{esc(sub)}</div>' if sub else "") + '</div>' + typed + '</div>')
        if yr:
            ty0 = round(t0 + IN + 0.1, 3); tdur = round(max(0.2, min(0.14 * len(yr), t1 - OUT - 0.4 - ty0)), 3)
            js += [typing(f"{sid}ty", yr, ty0, tdur)] + blink(f"#{sid}c", ty0 + tdur, t1 - OUT)
    elif kind == "quote":
        text = str(s.get("text", ""))
        if behind:
            ws = text.split()   # one line, 80 % wide: each word its own span (0.1em padding a side when serif, 0.24em gaps), plus push-in and drift
            px = (min(460, text_px("".join(ws), SERIF_TTF, W * 0.8, pad=0.2 * len(ws) + 0.24 * (len(ws) - 1))) if G and SERIF_TTF else
                  fit_px(text, W * 0.8, cap=460, serif=G, heading=not G))
            body = f'<div class="quote one" style="font-size: {px}px">' + "".join(f'<span class="qw"><span class="{"gserif" if G else "hbig"}">{esc(w)}</span></span>' for w in text.split()) + '</div>'
        else:
            px = fit_px(text, BW * 1.9, cap=150, serif=True) if G else fit_px(text, (BW - 60) * 1.9, cap=96)   # two lines at most
            inner = "".join(f'<span class="qw"><span class="gserif">{esc(w)}</span></span>' if G else f'<span class="qw">{esc(w)}</span>' for w in text.split())
            body = f'<div class="quote{"" if G else " hblock"}" style="font-size: {px}px">{inner}</div>'
            js.append(f'tl.fromTo("#{sid} .qw", {{ opacity: 0, y: 30, filter: "blur(12px)" }}, {{ opacity: 1, y: 0, filter: "blur(0px)", duration: {IN}, ease: "power3.out", stagger: 0.06 }}, {t0});')
    elif kind == "logo":
        name = s.get("src", "")
        src = next((p for p in [ROOT / "library" / name, ROOT / "library/Logos" / name, job / name, ROOT / name] if name and p.is_file()), None)
        if src is None:
            print(f"warning: scene {s.get('id', i)}: logo {name!r} not in library/Logos (Drive: OVS Claude Edit/Library/Logos); scene skipped")
            continue
        (proj / "assets/logos").mkdir(parents=True, exist_ok=True); shutil.copy(src, proj / "assets/logos" / src.name)
        img = f'<img id="{sid}img" class="logo" src="assets/logos/{src.name}" alt="" style="max-width: {round(W * 0.8 if behind else BW * 0.7)}px; max-height: {520 if behind else 260}px" />'
        body = f'<div class="gcard">{img}</div>' if G and not behind else img
        js.append(f'tl.fromTo("#{sid}img", {{ scale: 0.9 }}, {{ scale: 1, duration: 0.6, ease: "back.out(1.7)" }}, {t0});')
    elif kind == "typed":
        text, mode = str(s.get("text", "")), s.get("mode", "prompt")
        ty0 = round(t0 + IN + 0.1, 3); tdur = round(max(0.3, min(type_len(text), t1 - OUT - 0.5 - ty0)), 3)
        label = f'<div class="{"glabel" if G else "hpill"}">{esc(s.get("label", "Prompt" if mode == "prompt" else "Notes"))}</div>'
        line = f'<div class="tyline"><span id="{sid}ty" data-text="{esc(text)}">{esc(text)}</span><i id="{sid}c" class="caret"></i></div>'
        if mode == "prompt":
            send = (f'<b id="{sid}send" class="send"><svg viewBox="0 0 24 24" width="34" height="34"><path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="currentColor" '
                    f'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg></b>')
            body = f'<div class="{card} typed" style="width: {BW}px">{label}<div class="tyrow">{line}{send}</div></div>'
            js.append(f'tl.fromTo("#{sid}send", {{ scale: 0.6, opacity: 0.3 }}, {{ scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }}, {round(ty0 + tdur + 0.05, 3)});')
        else:
            body = f'<div class="{card} typed notes" style="width: {BW}px">{label}{line}</div>'
        js += [typing(f"{sid}ty", text, ty0, tdur)] + blink(f"#{sid}c", ty0 + tdur, t1 - OUT)
    else:  # lowerthird: lt-color-block (house) / a glass plate with a gradient bar (glow)
        nm, role = esc(s.get("name", "")), esc(s.get("role", ""))
        body = (f'<div class="gcard lt"><i class="ltbar"></i><div><div class="gsans ltname">{nm}</div>' + (f'<div class="glabel">{role}</div>' if role else "") + '</div></div>' if G else
                f'<div class="ltcol"><div class="hblock ltname">{nm}</div>' + (f'<div class="hrole">{role}</div>' if role else "") + '</div>')
    host = (f'<div id="{sid}" class="clip scene {pos}{" left" if kind == "lowerthird" else ""}{" behind" if behind else ""}" data-start="{t0}" '
            f'data-duration="{round(t1 - t0, 3)}" data-track-index="{2 if behind else 6 + i % 2}"><div id="{sid}in" class="sc-in">{body}</div></div>')
    if behind:  # caption-parallax-layers: in from 1.18, a slow drift, out clean; the people cutout goes over it
        scene_behind.append("        " + host); behind_spans.append((t0, t1))
        scene_js += [f'tl.fromTo("#{sid}in", {{ scale: {I["scaleFrom"]}, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: {I["durationSec"]}, ease: "{I["ease"]}" }}, {t0});',
                     f'tl.fromTo("#{sid}in", {{ scale: 1 }}, {{ immediateRender: false, scale: {1 + D["scale"]}, duration: {round(max(0.05, t1 - t0 - I["durationSec"] - OUT), 3)}, ease: "none" }}, {round(t0 + I["durationSec"], 3)});',
                     f'tl.fromTo("#{sid}in", {{ opacity: 1 }}, {{ opacity: 0, duration: {OUT}, ease: "power2.in", immediateRender: false }}, {round(t1 - OUT, 3)});']
    else:  # fast in (ease-out), hold, clean out before the next scene
        ax, d0 = ("x", -48) if kind == "lowerthird" else ("y", 36)
        scene_front.append("      " + host)
        scene_js += [f'tl.fromTo("#{sid}in", {{ opacity: 0, {ax}: {d0}, scale: 0.96 }}, {{ opacity: 1, {ax}: 0, scale: 1, duration: {IN}, ease: "power3.out" }}, {t0});',
                     f'tl.fromTo("#{sid}in", {{ opacity: 1, {ax}: 0 }}, {{ opacity: 0, {ax}: -16, duration: {OUT}, ease: "power2.in", immediateRender: false }}, {round(t1 - OUT, 3)});']
    scene_js += js
    scene_starts.append(t0)
    if s.get("punch", True):
        scene_punch.add(t0)

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
    "scenes": scene_starts,
}


def overlay(tr):
    """A transition clip from library/Transitions copied into assets/transitions/, with its sidecar <name>.json:
    (file name, markFrame, blend, frames) or None when the file isn't there."""
    f = tr.get("file", "")
    src = next((p for p in [ROOT / "library/Transitions" / f, job / f, ROOT / f] if f and p.is_file()), None)
    if src is None:
        print(f"warning: transition file {f!r} not in library/Transitions (Drive: OVS Claude Edit/Library/Transitions); skipped")
        return None
    side = src.with_suffix(".json")
    meta = json.loads(side.read_text()) if side.exists() else {}
    frames = meta.get("frames")
    if not frames:  # length from the file itself
        frames = round(30 * float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                                                 capture_output=True, text=True).stdout.strip() or 1))
    (proj / "assets/transitions").mkdir(parents=True, exist_ok=True); shutil.copy(src, proj / "assets/transitions" / src.name)
    return src.name, tr.get("markFrame", meta.get("markFrame", frames // 2)), tr.get("blend", meta.get("blend", "screen")), frames


flash_js, punch_extra, sfx, trans_html = [], set(), [], []
for tr in T:
    times = sorted({round(x, 3) for x in cut_points.get(tr.get("where", "every"), []) if 0 < x < total})
    look = tr.get("look", "flash2")
    for x in times:
        if look in ("flash2", "whiteflash"):
            fd = round(tr.get("frames", 2) / 30 * (3 if look == "whiteflash" else 1), 3)
            flash_js.append(f'tl.fromTo("#flash", {{ opacity: {tr.get("strength", 58) / 100} }}, {{ opacity: 0, duration: {fd}, ease: "none", immediateRender: false }}, {x});')
        elif look == "punch":
            punch_extra.add(x)
    ov = overlay(tr) if look == "overlay" and times else None
    for x in times if ov else []:  # the overlay's markFrame lands on the cut; screen / lighten blend it over the picture
        name, mark, blend, frames = ov
        st = round(x - mark / 30, 3); ms = round(max(0.0, -st), 3); st = max(0.0, st)
        d = round(min(frames / 30 - ms, total - st), 3)
        if d > 0:
            n = len(trans_html)
            trans_html.append(f'      <video id="tr{n}" class="clip trans" src="assets/transitions/{name}" muted playsinline data-start="{st}" data-media-start="{ms}" data-duration="{d}" '
                              f'data-track-index="{21 + n % 4}" style="mix-blend-mode: {blend}; opacity: {tr.get("strength", 100) / 100}"></video>')
    snd = tr.get("sound")
    if snd == "whoosh.wav" and tr.get("where") == "scenes" and AU.get("sfxPalette") == "kit":
        snd = None  # the kit palette already whooshes on every scene start
    if snd and times:
        src = next((p for p in [ROOT / "library/Sounds" / snd, ROOT / "library" / snd, TEMPLATE / "assets/sfx" / snd] if p.exists()), None)
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

# ---------- camera: slow push across each take, punch-ins / settles on chosen cuts and scene starts ----------
punch = {at(p) for p in E.get("punch", [])} | punch_extra | scene_punch
settle = {at(p) for p in E.get("settle", [])}
P, S, Z = STYLE["cuts"]["punchIn"], STYLE["cuts"]["scaleOutSettle"], STYLE["cuts"]["talkingHead"]["slowZoom"]
drift_p, drift_s = round(P["to"] * 1.03, 3), 1.04
if THEME == "glow":  # Soft Glow: subtle push-ins, never past motion.pushMaxPct, no shaky zooms
    capz = round(1 + MO["pushMaxPct"] / 100, 3)
    P, S, Z = dict(P, to=min(P["to"], capz)), dict(S, **{"from": min(S["from"], capz)}), dict(Z, to=min(Z["to"], capz))
    drift_p, drift_s = min(drift_p, capz), min(drift_s, capz)
PALETTE = AU.get("sfxPalette", "house")
cam = []
whoosh = E.get("sfx", AU.get("whoosh", True)) and PALETTE != "kit"   # the kit palette whooshes on scene changes instead
bounds = sorted({round(t["at"], 3) for t in takes} | punch | settle)
starts = {round(t["at"], 3): t["dur"] for t in takes}
zt = Z["to"]
for i, t0 in enumerate(bounds):
    t1 = bounds[i + 1] if i + 1 < len(bounds) else total
    d = max(0.05, t1 - t0)
    if t0 in punch:  # a punch inside a take starts from where the take's push has got to (no jump back)
        pf = min(zt, P["to"]) if t0 not in starts else P["from"]
        cam.append(f'tl.fromTo("#cam", {{ scale: {pf} }}, {{ scale: {P["to"]}, duration: {P["durationSec"]}, ease: "{P["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: {P["to"]} }}, {{ immediateRender: false, scale: {drift_p}, duration: {max(0.05, d - P["durationSec"]):.3f}, ease: "none" }}, {t0 + P["durationSec"]:.3f});')
        whoosh and sfx.append(("whoosh.wav", t0 - 0.12, 0.3))
    elif t0 in settle:
        cam.append(f'tl.fromTo("#cam", {{ scale: {S["from"]} }}, {{ scale: {S["to"]}, duration: {S["durationSec"]}, ease: "{S["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: 1 }}, {{ immediateRender: false, scale: {drift_s}, duration: {max(0.05, d - S["durationSec"]):.3f}, ease: "none" }}, {t0 + S["durationSec"]:.3f});')
        whoosh and sfx.append(("whoosh.wav", t0 - 0.12, 0.3))
    else:  # the push keeps the take's pace when a punch / settle cuts it short (no squeezed zoom)
        zt = round(Z["from"] + (Z["to"] - Z["from"]) * min(1, d / max(starts.get(t0, d), 0.05)), 4)
        cam.append(f'tl.fromTo("#cam", {{ scale: {Z["from"]} }}, {{ scale: {zt}, duration: {d:.3f}, ease: "none" }}, {t0});')

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
        inner = " ".join(f'<span class="k">{esc(x)}</span>' if norm(x) in keys else esc(x) for x in txt.split()) if GLOW else html.escape(txt)  # glow: key words in the gradient
        spans.append(f'<span id="card{ci}g{gi}" class="cardline">{inner}</span>')
        g1 = grp[gi + 1][0]["t0"] if gi + 1 < len(grp) else c1
        card_js.append(f'tl.set("#card{ci}g{gi}", {{ visibility: "visible" }}, {g[0]["t0"]}); tl.set("#card{ci}g{gi}", {{ visibility: "hidden" }}, {round(g1, 3)});')
    fs = round(SK.get("size", 5.4) * H / 100)
    if GLOW:  # near-black with a soft warm glow behind the words
        bg = f"radial-gradient(70% 42% at 50% 46%, {rgba(LOOK['glow'], 0.24)}, {rgba(LOOK['glow'], 0)} 72%), {bg}"
    card_html.append(f'      <div id="card{ci}" class="clip card" data-start="{c0}" data-duration="{round(c1 - c0, 3)}" data-track-index="8" '
                     f'style="background: {bg}; color: {ink}; font: {"italic " if SK.get("italic") else ""}{SK.get("weight", 800)} {fs}px/1.04 &quot;{card_font}&quot;, sans-serif; letter-spacing: {SK.get("spacing", -5.5) / 100}em; '
                     f'text-transform: {CASE[SK.get("case", "lower")]}; text-align: {SK.get("align", "center")}">{"".join(spans)}</div>')

# ---------- word or logo behind the subjects (caption-parallax-layers recipe), once per video ----------
hero_html, hero_js, cut_spans = "", "", []
h = E.get("hero")
if h:
    t0, t1 = at(h["seg"]), seg_end(h["seg"])
    if h.get("logo"):
        inner = f'<img id="heroWord" src="{h["logo"]}" alt="" style="width: {round(W * 0.8)}px" />'
    elif GLOW:  # the word as written, serif italic in the look gradient (on the inner span: #heroWord scales)
        px = min(460, text_px(h["word"], SERIF_TTF, W * STYLE["textBehindSubject"]["fitWidthPct"] / 100, pad=0.2)) if SERIF_TTF else 300
        inner = f'<span id="heroWord" style="font-size: {px}px"><span class="gserif">{esc(h["word"])}</span></span>'
    else:
        from PIL import ImageFont
        f = ImageFont.truetype(str(TEMPLATE / "assets/fonts/Archivo-Variable.ttf"), 200)
        want = {b"Weight": STYLE["fonts"]["heading"]["weight"], b"Width": STYLE["fonts"]["heading"]["width"]}
        f.set_variation_by_axes([want.get(ax["name"], ax["default"]) for ax in f.get_variation_axes()])
        l, _, r, _ = f.getbbox(h["word"].upper())
        px = round(200 * W * STYLE["textBehindSubject"]["fitWidthPct"] / 100 / (r - l), 1)
        inner = f'<span id="heroWord" style="font-size: {px}px">{html.escape(h["word"].upper())}</span>'
    hero_html = f'        <div id="hero" class="clip" data-start="{t0}" data-duration="{round(t1 - t0, 3)}" data-track-index="2">{inner}</div>'
    hero_js = (f'tl.fromTo("#heroWord", {{ scale: {I["scaleFrom"]}, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: {I["durationSec"]}, ease: "{I["ease"]}" }}, {t0});\n'
               f'      tl.fromTo("#heroWord", {{ scale: 1 }}, {{ immediateRender: false, scale: {1 + D["scale"]}, duration: {round(t1 - t0 - I["durationSec"], 3)}, ease: "none" }}, {round(t0 + I["durationSec"], 3)});')
    cut_spans.append((t0, t1))
cutouts = []
for c0, c1 in sorted(cut_spans + behind_spans):  # one cutout per stretch that needs the people in front (overlaps merged)
    if cutouts and c0 <= cutouts[-1][1] + 0.05:
        cutouts[-1][1] = max(cutouts[-1][1], c1)
    else:
        cutouts.append([c0, c1])
cutout_html = [f'        <video id="cutout{i or ""}" class="clip" src="assets/cutout_{i}.webm" data-start="{c0}" data-media-start="0" data-duration="{round(c1 - c0, 3)}" '
               f'data-track-index="3" muted playsinline data-layout-allow-occlusion></video>' for i, (c0, c1) in enumerate(cutouts)]
if cutouts:  # edit.sh makes assets/cutout_<i>.webm for each span (matte.py)
    (proj / "cutout.json").write_text(json.dumps({"spans": [{"start": c0, "end": c1, "file": f"cutout_{i}.webm"} for i, (c0, c1) in enumerate(cutouts)]}))
cam_html = "\n".join([x for x in [hero_html] if x] + scene_behind + cutout_html)

# ---------- sound: house = whoosh on punch-ins + pop on key words; kit = hit, taps, whooshes, chime ----------
if PALETTE == "kit":
    if E.get("sfx", True):  # the 5-Pass kit: hit on the hook, tap on each item, whoosh on scene changes, chime to close
        kit = [("hit.wav", 0, 0.5)] + [("whoosh.wav", t - 0.12, 0.3) for t in scene_starts] + [("tap.wav", t, 0.35) for t in item_times] + [("chime.wav", total - 0.6, 0.4)]
        missing = sorted({n for n, _, _ in kit if not (TEMPLATE / "assets/sfx" / n).exists()})
        missing and print(f"warning: {', '.join(missing)} not in templates/ovs-vertical/assets/sfx (scripts/make_sfx.py makes them); left out")
        sfx += [x for x in kit if x[0] not in missing]
elif E.get("sfx", AU.get("pop", True)):
    last = -9
    for w in words:
        if w["key"] and w["start"] - last >= 1.5:
            sfx.append(("pop.wav", w["start"], 0.28)); last = w["start"]
SFX_LEN = {"pop.wav": 0.5, "whoosh.wav": 0.5, "tap.wav": 0.5, "hit.wav": 1.0}
sfx_html = "\n".join(f'      <audio id="sfx{i}" class="clip" src="assets/sfx/{n}" data-start="{max(0, round(t, 3))}" data-duration="{min(SFX_LEN.get(n, 1.5), round(total - max(0, t), 3))}" data-volume="{v}" data-track-index="{30 + i % 8}"></audio>'
                     for i, (n, t, v) in enumerate(sorted(sfx, key=lambda x: x[1])))
mu = music_plan()
if mu and not (proj / "assets/music.m4a").exists():
    print("note: music is set but assets/music.m4a isn't made yet (scripts/edit.sh step e runs scripts/music.py)")
music_html = (f'\n      <audio id="music" class="clip" src="assets/music.m4a" data-start="0" data-duration="{total}" data-volume="1" data-track-index="29"></audio>'
              if mu and (proj / "assets/music.m4a").exists() else "")

# ---------- hook: focus-blur-resolve, the first spoken line on screen from frame 1 ----------
HK = STYLE["hook"]["text"]
hk = {norm(k) for k in E.get("hookKeys", [])}
hook_text = E["hookText"] if GLOW and SC.get("case", "upper") == "none" else E["hookText"].lower() if GLOW and SC.get("case") == "lower" else E["hookText"].upper()
hook_words = "".join(f'<span class="{"key" if norm(w) in hk else ""}">{html.escape(w)}</span>' for w in hook_text.split())
heroc = (h or {}).get("colour", STYLE["colors"]["accent"])
if GLOW:  # support words in the caption sans, the key word in the serif italic gradient (one idea, two faces)
    hook_css = (f'.hf-catalog-focus-blur-resolve {{ display: flex; flex-wrap: wrap; justify-content: center; align-items: baseline; align-content: center; gap: 0 16px; max-width: {W - 2 * L["mx"]}px; text-align: center; color: {LOOK["text"]}; font: {cap_weight} {round(L["hook"] * 0.78)}px/1.08 "{cap_font}", sans-serif; letter-spacing: -0.015em; transform-origin: 50% 50%; text-shadow: 0 4px 22px rgba(0,0,0,0.5); }}\n'
                f'      .hf-catalog-focus-blur-resolve span {{ display: inline-block; filter: blur(calc(var(--hf-word-blur, 0px))); }}\n'
                f'      .hf-catalog-focus-blur-resolve span.key {{ font: italic 400 {KEY_SCALE}em/0.95 "{KEY_FONT}", serif; background: {GRAD}; -webkit-background-clip: text; background-clip: text; color: transparent; text-shadow: none; padding: 0 0.1em; filter: blur(calc(var(--hf-word-blur, 0px))) drop-shadow(0 4px 16px rgba(0,0,0,0.45)); }}')
    hero_css = '#heroWord { display: inline-block; line-height: 1.1; white-space: nowrap; transform-origin: 50% 50%; }'
else:
    hook_css = (f'.hf-catalog-focus-blur-resolve {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 4px 18px; max-width: {W - 2 * L["mx"]}px; text-align: center; color: #fff; font: 900 {L["hook"]}px/1.02 "Inter", sans-serif; letter-spacing: -0.02em; transform-origin: 50% 50%; -webkit-text-stroke: {C["strokePx"]}px {C["strokeColor"]}; paint-order: stroke fill; text-shadow: {C["shadow"]}; }}\n'
                f'      .hf-catalog-focus-blur-resolve span {{ display: inline-block; filter: blur(calc(var(--hf-word-blur, 0px))); }}\n'
                f'      .hf-catalog-focus-blur-resolve span.key {{ background: var(--accent); color: var(--accent-ink); -webkit-text-stroke: 0; text-shadow: none; border-radius: 10px; padding: 0 14px; }}')
    hero_css = f'#heroWord {{ display: inline-block; font-family: "Archivo", "Arial Black", sans-serif; font-weight: 900; font-stretch: {STYLE["fonts"]["heading"]["width"]}%; color: {heroc}; line-height: 1; white-space: nowrap; transform-origin: 50% 50%; }}'

# ---------- styles only the new pieces need (nothing for a house video without scenes / overlays) ----------
faces = []
for fam in ([KEY_FONT] if GLOW or G else []) + ([card_font] if GLOW and card_html else []) + ([LOOK["labelFont"]] if G and scenes else []):
    faces += [r for r in font_faces(fam) if r not in faces]
css = []
if GLOW or (G and scenes):
    css.append(f'.gserif {{ font-family: "{KEY_FONT}", serif; font-style: italic; font-weight: 400; line-height: 1; background: {GRAD}; -webkit-background-clip: text; background-clip: text; color: transparent; padding: 0 0.1em; }}')
if GLOW and card_html:
    css.append(f'.card .k {{ background: {GRAD}; -webkit-background-clip: text; background-clip: text; color: transparent; padding: 0 0.08em; }}')
if len(cutouts) > 1:
    css.append(", ".join(f"#cutout{i}" for i in range(1, len(cutouts))) + f" {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 3; }}")
if trans_html:  # above the footage, B-roll, scenes and cards; under the captions
    css.append(f".trans {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 9; pointer-events: none; }}")
if scenes:
    t, mu_c = (LOOK["text"], LOOK["muted"]) if G else ("#0D0E0C", "#5F5D57")
    css += [f".scene {{ position: absolute; left: {L['mx']}px; right: {L['mx']}px; display: flex; justify-content: center; z-index: 7; pointer-events: none; }}",
            f".scene.top {{ top: {STOP}px; align-items: flex-start; }}",
            f".scene.middle, .scene.lower {{ bottom: {H - SBOT}px; align-items: flex-end; }}",
            f".scene.hero {{ left: 0; right: 0; top: {L['heroY'] - 260}px; height: 520px; align-items: center; }}",
            ".scene.behind { z-index: 2; }  .scene.left { justify-content: flex-start; }",
            ".sc-in { display: flex; flex-direction: column; align-items: center; gap: 22px; max-width: 100%; transform-origin: 50% 50%; }  .scene.left .sc-in { align-items: flex-start; transform-origin: 0% 50%; }",
            ".num { display: inline-block; white-space: nowrap; line-height: 1; }",
            ".srow, .src { display: flex; align-items: center; gap: 30px; text-align: left; }  .slab { font-size: 40px; max-width: 320px; line-height: 1.1; }  .scol { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }",
            ".tiles { display: grid; gap: 28px; justify-content: center; }  .tile { display: flex; flex-direction: column; align-items: center; gap: 16px; }",
            f".rows {{ display: flex; flex-direction: column; gap: 16px; width: {BW}px; }}  .grow, .hrow {{ display: flex; align-items: center; gap: 24px; }}",
            f".stack {{ position: relative; width: {BW}px; }}  .stack > .note {{ position: absolute; left: 0; right: 0; top: 0; display: flex; gap: 22px; align-items: center; padding: 22px 26px; }}",
            ".nicon { flex: 0 0 76px; height: 76px; border-radius: 20px; display: flex; align-items: center; justify-content: center; font: 800 38px/1 \"Inter\", sans-serif; }",
            ".ntext { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }  .nhead { display: flex; justify-content: space-between; }",
            f".ntitle {{ font: 700 34px/1.15 \"Inter\", sans-serif; color: {t}; }}  .nbody {{ font: 500 31px/1.2 \"Inter\", sans-serif; color: {mu_c}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}",
            ".yr { display: flex; align-items: center; line-height: 1; }  .caret { display: inline-block; width: 0.07em; height: 0.8em; margin-left: 0.05em; vertical-align: -0.08em; }",
            ".tyrow { display: flex; align-items: flex-end; gap: 22px; width: 100%; }  .tyline { flex: 1; min-height: 1.35em; text-align: left; white-space: pre-wrap; }",
            ".send { flex: 0 0 68px; height: 68px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }  .typed { display: flex; flex-direction: column; align-items: flex-start; gap: 18px; }",
            ".quote { display: flex; flex-wrap: wrap; justify-content: center; gap: 0 0.24em; text-align: center; line-height: 1.04; }  .quote.one { flex-wrap: nowrap; white-space: nowrap; }  .qw { display: inline-block; }",
            ".lt { display: flex; align-items: stretch; gap: 24px; padding: 26px 44px 26px 26px; }  .ltcol { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }",
            ".logo { display: block; object-fit: contain; }"]
    if G:  # Soft Glow: near-black glass with a warm glow, gradient accents, mono labels, serif italic hero text
        css += [f'.gcard {{ position: relative; background: linear-gradient(180deg, {rgba(LOOK["bg"], 0.9)}, {rgba(LOOK["bg"], 0.82)}); border: 1.5px solid rgba(255,255,255,0.1); border-radius: 34px; box-shadow: 0 30px 70px rgba(0,0,0,0.45), 0 0 120px {rgba(LOOK["glow"], 0.2)}; color: {LOOK["text"]}; padding: 36px 48px; }}',
                f'.glabel {{ font: 500 24px/1.25 "{LOOK["labelFont"]}", monospace; letter-spacing: 0.24em; text-transform: uppercase; color: {LOOK["muted"]}; }}',
                f'.sc-in > .glabel, .tile .glabel {{ color: {LOOK["text"]}; font-weight: 700; font-size: 26px; text-shadow: 0 2px 12px rgba(0,0,0,0.8); }}',
                f'.gsans {{ font-family: "Inter", sans-serif; font-weight: 600; color: {LOOK["text"]}; letter-spacing: -0.01em; line-height: 1.15; }}',
                f'.gicon {{ position: relative; display: flex; align-items: center; justify-content: center; border-radius: 28%; background: linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02)), {LOOK["bg"]}; border: 1.5px solid rgba(255,255,255,0.12); box-shadow: 0 20px 50px rgba(0,0,0,0.45), 0 0 80px {rgba(LOOK["glow"], 0.18)}; }}',
                f'.gring {{ position: absolute; inset: -8px; border-radius: 30%; box-shadow: 0 0 0 3px {LOOK["gradient"][1]}, 0 0 44px {rgba(LOOK["gradient"][1], 0.6)}; opacity: 0; }}',
                '.grow { padding: 24px 34px; border-radius: 26px; }  .grow .gsans { font-size: 44px; }  .note.gcard { padding: 22px 26px; border-radius: 30px; }',
                f'.gcard .nicon {{ background: {GRAD}; color: {LOOK["bg"]}; }}  .gcard .nhead {{ font: 500 22px/1.2 "{LOOK["labelFont"]}", monospace; letter-spacing: 0.18em; text-transform: uppercase; color: {LOOK["muted"]}; }}',
                '.src .stitle { font-size: 46px; }  .src .yr { font-size: 124px; }  .gcard.srow { padding: 30px 44px; }',
                f'.caret {{ background: {LOOK["gradient"][-1]}; }}  .tyline {{ font: 500 42px/1.35 "Inter", sans-serif; color: {LOOK["text"]}; }}  .send {{ background: {GRAD}; color: {LOOK["bg"]}; }}',
                f'.ltbar {{ width: 8px; border-radius: 4px; background: linear-gradient(180deg, {", ".join(LOOK["gradient"])}); }}  .ltname {{ font-size: 46px; margin-bottom: 6px; }}']
    else:  # house: yellow blocks, black Inter Black, white cards; big words behind in the Archivo heading
        A_, INK = STYLE["colors"]["accent"], STYLE["colors"]["accentInk"]
        css += [f'.hblock {{ background: {A_}; color: {INK}; border-radius: 16px; padding: 14px 30px; font-family: "Inter", sans-serif; font-weight: 900; text-transform: uppercase; letter-spacing: -0.01em; line-height: 1; }}',
                f'.hcap {{ font-family: "Inter", sans-serif; font-weight: 900; color: #fff; text-transform: uppercase; line-height: 1.05; text-align: center; -webkit-text-stroke: {C["strokePx"]}px {C["strokeColor"]}; paint-order: stroke fill; text-shadow: {C["shadow"]}; }}',
                '.hcard { background: #FFFFFF; color: #0D0E0C; border-radius: 26px; box-shadow: 0 22px 50px rgba(0,0,0,0.35); padding: 30px 40px; }',
                f'.hbig {{ font-family: "Archivo", "Arial Black", sans-serif; font-weight: 900; font-stretch: {STYLE["fonts"]["heading"]["width"]}%; color: {heroc}; text-transform: uppercase; line-height: 1; white-space: nowrap; }}',
                '.htile { display: flex; align-items: center; justify-content: center; text-align: center; padding: 10px; }',
                '.hrow { font-size: 46px; padding: 18px 28px; }  .hidx { display: inline-flex; align-items: center; justify-content: center; width: 1.3em; height: 1.3em; border-radius: 50%; background: #0D0E0C; color: ' + A_ + '; font-size: 0.62em; }',
                f'.hcard .nicon {{ background: {A_}; color: {INK}; }}  .hcard .nhead {{ font: 800 22px/1.2 "Inter", sans-serif; letter-spacing: 0.06em; text-transform: uppercase; color: #8A877F; }}  .note.hcard {{ padding: 22px 26px; border-radius: 28px; }}',
                f'.hpill {{ background: {A_}; color: {INK}; border-radius: 10px; padding: 8px 16px; font: 900 22px/1 "Inter", sans-serif; letter-spacing: 0.08em; text-transform: uppercase; }}',
                '.src .stitle { font: 900 44px/1.05 "Inter", sans-serif; text-transform: uppercase; }  .src .ssub { font: 700 28px/1.2 "Inter", sans-serif; color: #5F5D57; }  .src .yr { font: 900 112px/1 "Inter", sans-serif; }  .srow .slab { font-size: 48px; text-align: left; }',
                f'.caret {{ background: {INK}; }}  .tyline {{ font: 700 42px/1.35 "Inter", sans-serif; color: #0D0E0C; }}  .send {{ background: {A_}; color: {INK}; }}  .hcard.notes {{ background: #EFEAE0; }}',
                '.ltname { font-size: 50px; }  .hrole { background: #0D0E0C; color: #FFFFFF; border-radius: 10px; padding: 10px 18px; font: 800 26px/1 "Inter", sans-serif; letter-spacing: 0.04em; text-transform: uppercase; }']
font_css = "".join("\n      " + r for r in faces)
extra_css = "".join("\n      " + r for r in css)
scenes_js = "".join("\n      " + j for j in scene_js)
front_html = "".join("\n" + x for x in scene_front)
trans_out = "".join("\n" + x for x in trans_html)

index = f"""<!doctype html>
<html lang="en" data-resolution="{'portrait' if H > W else 'landscape'}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Archivo"; src: url("assets/fonts/Archivo-Variable.ttf") format("truetype"); font-weight: 100 900; font-stretch: 62% 125%; font-display: block; }}{font_css}
      :root {{ --accent: {STYLE["colors"]["accent"]}; --accent-ink: {STYLE["colors"]["accentInk"]}; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #bg {{ position: absolute; inset: 0; background: {LOOK["bg"] if GLOW else "#000"}; }}
      #cam {{ position: absolute; inset: 0; transform-origin: 50% 35%; overflow: hidden; }}
      #aroll, #cutout {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      #cutout {{ z-index: 3; }}
      #hero {{ position: absolute; left: 0; right: 0; top: {L["heroY"] - 260}px; height: 520px; display: flex; align-items: center; justify-content: center; z-index: 2; }}
      {hero_css}
      #captions {{ z-index: 10; }}
      .broll {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 5; }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; z-index: 20; }}
      .card {{ position: absolute; inset: 0; z-index: 9; display: flex; align-items: center; justify-content: center; padding: 0 {L["mx"]}px; }}
      .cardline {{ position: absolute; left: {L["mx"]}px; right: {L["mx"]}px; visibility: hidden; }}
      #hook {{ position: absolute; left: {L["mx"]}px; right: {L["mx"]}px; top: {L["hookY"] - 150}px; height: 300px; display: flex; align-items: center; justify-content: center; z-index: 12; }}
      {hook_css}{extra_css}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
      <div id="bg" class="clip" data-start="0" data-duration="{total}" data-track-index="0"></div>
      <div id="cam">
        <video id="aroll" class="clip" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{total}" data-has-audio="true" data-track-index="1" playsinline></video>
{cam_html}
      </div>
{chr(10).join(broll_html)}{front_html}
{chr(10).join(card_html)}{trans_out}
      <div id="captions" data-composition-src="compositions/components/caption-highlight.html" data-composition-id="caption-highlight" data-start="0" data-duration="{total}" data-track-index="10"></div>
      <div id="hook" class="clip" data-start="0" data-duration="{hook_end}" data-track-index="13"><div class="hf-catalog-focus-blur-resolve">{hook_words}</div></div>
{flash_html}
{sfx_html}{music_html}
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
      {hero_js}{scenes_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
(proj / "index.html").write_text(index)
print(f"{proj / 'index.html'}  {W}x{H}, {total}s, {LOOK['name']} look, {len(groups)} caption groups, {sum(w['key'] for w in words)} key words, "
      f"{len(scene_front) + len(scene_behind)} scenes, {len(cutouts)} cutout spans, {len(trans_html)} overlays, {len(sfx)} sfx{', music' if music_html else ''}")
