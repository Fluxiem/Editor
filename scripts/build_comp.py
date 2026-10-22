#!/usr/bin/env python3
"""Generate a house-style HyperFrames composition from a cut list and an edit spec.

Usage: build_comp.py PROJECT_DIR CUTS.json EDIT.json [--aroll assets/aroll.mp4]

Writes PROJECT_DIR/index.html plus per-project copies of the restyled catalog blocks
(caption-highlight with this edit's words, lt-color-block with the lower-third text).
Times in EDIT.json are anchors resolved against CUTS.json, so the same spec works for every
hook variant:  "seg" = start of that segment's first take, "seg@word" = start of that word
(first match inside the segment), optional "+0.2" / "-0.2" offset.

EDIT.json keys: hookText, hookKeys[], chapters[{at,label}], punch[at], settle[at],
keys[] (caption words to highlight), broll[{src,at,dur,zoom,pos}], lowerThird{at,name,role},
hero{word,at,until,cutout,cutoutAt}, tail (seconds kept after the last word).
"""
import argparse, html, json, pathlib, re, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates/ovs-vertical"
STYLE = json.loads((ROOT / "style.json").read_text())
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())

ap = argparse.ArgumentParser()
ap.add_argument("project"); ap.add_argument("cuts"); ap.add_argument("edit"); ap.add_argument("--aroll", default="assets/aroll.mp4")
a = ap.parse_args()
proj = pathlib.Path(a.project)
cuts, E = json.load(open(a.cuts)), json.load(open(a.edit))
takes = cuts["takes"]
hook_end = sum(t["dur"] for t in takes if t["role"] == "hook")
last_word = max(w["t1"] for t in takes for w in t["words"])
total = round(min(cuts["duration"], last_word + E.get("tail", 0.25)), 3)


def at(ref):
    m = re.match(r"^([\w-]+)(?:@([^+-]+))?([+-][\d.]+)?$", ref)
    seg, word, off = m.group(1), m.group(2), float(m.group(3) or 0)
    ts = [t for t in takes if t["seg"] == seg]
    if not ts:
        raise SystemExit(f"no segment {seg!r}")
    if word is None:
        return round(ts[0]["at"] + off, 3)
    for t in ts:
        for w in t["words"]:
            if norm(w["w"]) == norm(word):
                return round(w["t0"] + off, 3)
    raise SystemExit(f"no word {word!r} in {seg!r}")


# ---------- captions: ≤3-word groups, break at punctuation and takes; skip the hook ----------
keys = {norm(k) for k in E.get("keys", [])}
words, groups = [], []
for t in takes:
    if t["role"] == "hook":
        continue
    cur = []
    for w in t["words"]:
        words.append({"text": w["w"].strip(), "start": w["t0"], "end": w["t1"], "key": norm(w["w"]) in keys})
        cur.append(len(words) - 1)
        if len(cur) == 3 or re.search(r"[.,!?]$", w["w"]):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
# at most one key word per group
for g in groups:
    ks = [i for i in g if words[i]["key"]]
    for i in ks[1:]:
        words[i]["key"] = False

comp = proj / "compositions"; (comp / "components").mkdir(parents=True, exist_ok=True)
cap = (TEMPLATE / "compositions/components/caption-highlight.html").read_text()
js_words = "[\n" + ",\n".join("          " + json.dumps({"text": w["text"], "start": w["start"], "end": w["end"], **({"key": True} if w["key"] else {})}) for w in words) + "\n        ]"
cap = re.sub(r"var WORDS = \[.*?\n        \];", "var WORDS = " + js_words + ";", cap, count=1, flags=re.S)
cap = re.sub(r"var RAW_GROUPS = \[.*?\n        \];", "var RAW_GROUPS = " + json.dumps([[g[0], g[-1]] for g in groups]) + ";", cap, count=1, flags=re.S)
cap = cap.replace("WORDS[RAW_GROUPS[gi + 1][0]].start : 8.0", f"WORDS[RAW_GROUPS[gi + 1][0]].start : {total}")
cap = cap.replace('data-duration="8"', f'data-duration="{total}"', 1)
(comp / "components/caption-highlight.html").write_text(cap)

# ---------- lower third ----------
lt = E.get("lowerThird")
if lt:
    s = (TEMPLATE / "compositions/lt-color-block.html").read_text()
    s = s.replace(">Dr. Maya Chen<", f">{html.escape(lt['name'])}<").replace(">Host · Neuroscientist<", f">{html.escape(lt['role'])}<")
    s = s.replace("bottom: 680px;", f"bottom: {lt.get('bottom', 840)}px;")  # sits above the caption line
    (comp / "lt-color-block.html").write_text(s)

# ---------- assets the blocks need ----------
for sub in ["assets/fonts", "assets/sfx"]:
    shutil.copytree(TEMPLATE / sub, proj / sub, dirs_exist_ok=True)
for f in ["hyperframes.json", "package.json", "meta.json"]:
    if not (proj / f).exists():
        shutil.copy(TEMPLATE / f, proj / f)

# ---------- camera moves per take ----------
punch = {at(p) for p in E.get("punch", [])}
settle = {at(p) for p in E.get("settle", [])}
P, S, Z = STYLE["cuts"]["punchIn"], STYLE["cuts"]["scaleOutSettle"], STYLE["cuts"]["talkingHead"]["slowZoom"]
cam, sfx = [], []
bounds = sorted({round(t["at"], 3) for t in takes} | punch)
for i, t0 in enumerate(bounds):
    t1 = bounds[i + 1] if i + 1 < len(bounds) else total
    d = max(0.05, t1 - t0)
    if t0 in punch:
        cam.append(f'tl.fromTo("#cam", {{ scale: {P["from"]} }}, {{ scale: {P["to"]}, duration: {P["durationSec"]}, ease: "{P["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: {P["to"]} }}, {{ immediateRender: false, scale: {round(P["to"] * 1.04, 3)}, duration: {max(0.05, d - P["durationSec"]):.3f}, ease: "none" }}, {t0 + P["durationSec"]:.3f});')
        sfx.append(("whoosh", t0 - 0.12, 0.35))
    elif t0 in settle:
        cam.append(f'tl.fromTo("#cam", {{ scale: {S["from"]} }}, {{ scale: {S["to"]}, duration: {S["durationSec"]}, ease: "{S["ease"]}" }}, {t0});')
        cam.append(f'tl.fromTo("#cam", {{ scale: 1 }}, {{ immediateRender: false, scale: 1.05, duration: {max(0.05, d - S["durationSec"]):.3f}, ease: "none" }}, {t0 + S["durationSec"]:.3f});')
        sfx.append(("whoosh", t0 - 0.12, 0.35))
    else:
        cam.append(f'tl.fromTo("#cam", {{ scale: {Z["from"]} }}, {{ scale: {Z["to"]}, duration: {d:.3f}, ease: "none" }}, {t0});')

# ---------- B-roll ----------
broll_html, broll_js = [], []
for i, b in enumerate(E.get("broll", [])):
    t0 = at(b["at"]); d = round(min(b.get("dur", 1.8), STYLE["graphics"]["popupMaxHoldSec"], total - t0), 3)
    broll_html.append(f'      <img id="broll{i}" class="clip broll" src="{b["src"]}" alt="" data-start="{t0}" data-duration="{d}" data-track-index="{5}" style="object-position: {b.get("pos", "50% 50%")}" />')
    z = b.get("zoom", 1.1)
    broll_js.append(f'tl.fromTo("#broll{i}", {{ scale: {z} }}, {{ scale: {round(z * 1.06, 3)}, duration: {d}, ease: "none" }}, {t0});')
    sfx.append(("whoosh", t0 - 0.12, 0.3))

# ---------- chapters ----------
chap_html, chap_js = [], []
for i, c in enumerate(E.get("chapters", [])):
    t0 = at(c["at"]); t1 = at(E["chapters"][i + 1]["at"]) if i + 1 < len(E["chapters"]) else total
    chap_html.append(f'      <div id="chap{i}" class="clip pill" data-start="{t0}" data-duration="{round(t1 - t0, 3)}" data-track-index="11">{html.escape(c["label"].upper())}</div>')
    chap_js.append(f'tl.fromTo("#chap{i}", {{ scale: 0.6, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }}, {t0});')

# ---------- hero word (text behind subject, once) ----------
hero_html, hero_js, hero_px = "", "", 200


def hero_font_px(word):
    """Font size that makes WORD (caps) span the target width in Archivo wdth 125 / wght 900."""
    from PIL import ImageFont
    f = ImageFont.truetype(str(TEMPLATE / "assets/fonts/Archivo-Variable.ttf"), 200)
    want = {b"Weight": STYLE["fonts"]["heading"]["weight"], b"Width": STYLE["fonts"]["heading"]["width"]}
    f.set_variation_by_axes([want.get(ax["name"], ax["default"]) for ax in f.get_variation_axes()])
    l, _, r, _ = f.getbbox(word.upper())
    return round(200 * 1080 * STYLE["textBehindSubject"]["fitWidthPct"] / 100 / (r - l), 1)
h = E.get("hero")
if h:
    t0, t1 = at(h["at"]), at(h["until"])
    hero_px = hero_font_px(h["word"])
    c0 = at(h["cutoutAt"])
    I, D = STYLE["textBehindSubject"]["in"], STYLE["textBehindSubject"]["drift"]
    hero_html = (f'        <div id="hero" class="clip" data-start="{t0}" data-duration="{round(t1 - t0, 3)}" data-track-index="2"><span id="heroWord" style="font-size: {hero_px}px">{html.escape(h["word"].upper())}</span></div>\n'
                 f'        <video id="cutout" class="clip" src="{h["cutout"]}" data-start="{c0}" data-media-start="0" data-duration="{round(t1 - c0, 3)}" data-track-index="3" muted playsinline data-layout-allow-occlusion></video>')
    hero_js = (f'tl.fromTo("#heroWord", {{ scale: {I["scaleFrom"]} }}, {{ scale: 1, duration: {I["durationSec"]}, ease: "{I["ease"]}" }}, {t0});\n'
               f'      tl.fromTo("#heroWord", {{ scale: 1 }}, {{ immediateRender: false, scale: {1 + D["scale"]}, duration: {round(t1 - t0 - I["durationSec"], 3)}, ease: "none" }}, {round(t0 + I["durationSec"], 3)});')
    sfx.append(("pop", t0, 0.5))

# key-word pops (not on the hero word, max one per 1.5 s)
last = -9
for w in words:
    if w["key"] and w["start"] - last >= 1.5 and not (h and norm(w["text"]) == norm(h["word"])):
        sfx.append(("pop", w["start"], 0.28)); last = w["start"]

lt_html = (f'      <div id="lt" data-composition-src="compositions/lt-color-block.html" data-composition-id="lt-color-block" data-start="{at(lt["at"])}" data-duration="4.8" data-track-index="12"></div>' if lt else "")
sfx_html = "\n".join(f'      <audio id="sfx{i}" class="clip" src="assets/sfx/{n}.wav" data-start="{max(0, round(t, 3))}" data-duration="0.5" data-volume="{v}" data-track-index="{30 + i % 8}"></audio>' for i, (n, t, v) in enumerate(sorted(sfx, key=lambda x: x[1])))

HK = STYLE["hook"]["text"]
hook_words = "".join(f'<span class="{"key" if norm(w) in {norm(k) for k in E.get("hookKeys", [])} else ""}">{html.escape(w)}</span>' for w in E["hookText"].upper().split())
CAPS = STYLE["captions"]

index = f"""<!doctype html>
<html lang="en" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Archivo"; src: url("assets/fonts/Archivo-Variable.ttf") format("truetype"); font-weight: 100 900; font-stretch: 62% 125%; font-display: block; }}
      :root {{ --accent: {STYLE["colors"]["accent"]}; --accent-ink: {STYLE["colors"]["accentInk"]}; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #000; }}
      #bg {{ position: absolute; inset: 0; background: #000; }}
      #cam {{ position: absolute; inset: 0; transform-origin: 50% 35%; overflow: hidden; }}
      #aroll, #cutout {{ position: absolute; inset: 0; width: 1080px; height: 1920px; object-fit: cover; }}
      #cutout {{ z-index: 3; }}
      #hero {{ position: absolute; left: 0; right: 0; top: {STYLE["textBehindSubject"]["centerY"] - 200}px; height: 400px; display: flex; align-items: center; justify-content: center; z-index: 2; }}
      #heroWord {{ display: inline-block; font-family: "Archivo", "Arial Black", sans-serif; font-weight: 900; font-stretch: {STYLE["fonts"]["heading"]["width"]}%; color: var(--accent); line-height: 1; white-space: nowrap; transform-origin: 50% 50%; }}
      #captions {{ z-index: 10; }} #lt {{ z-index: 12; }}
      .broll {{ position: absolute; inset: 0; width: 1080px; height: 1920px; object-fit: cover; z-index: 5; }}
      .pill {{ position: absolute; left: {STYLE["chapterPill"]["x"]}px; top: {STYLE["chapterPill"]["y"]}px; background: var(--accent); color: var(--accent-ink); font: 900 {STYLE["chapterPill"]["sizePx"]}px "Inter", sans-serif; letter-spacing: 0.04em; padding: {STYLE["chapterPill"]["paddingPx"][0]}px {STYLE["chapterPill"]["paddingPx"][1]}px; border-radius: {STYLE["chapterPill"]["radiusPx"]}px; transform-origin: 0 50%; z-index: 11; }}
      #hook {{ position: absolute; left: {STYLE["safeZone"]["xMin"]}px; right: {1080 - STYLE["safeZone"]["xMax"]}px; top: 1010px; height: 300px; display: flex; align-items: center; justify-content: center; z-index: 12; }}
      .hf-catalog-focus-blur-resolve {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 4px 18px; max-width: 840px; text-align: center; color: #fff; font: 900 92px/1.02 "Inter", sans-serif; letter-spacing: -0.02em; transform-origin: 50% 50%; -webkit-text-stroke: {CAPS["strokePx"]}px {CAPS["strokeColor"]}; paint-order: stroke fill; text-shadow: {CAPS["shadow"]}; }}
      .hf-catalog-focus-blur-resolve span {{ display: inline-block; filter: blur(calc(var(--hf-word-blur, 0px))); }}
      .hf-catalog-focus-blur-resolve span.key {{ background: var(--accent); color: var(--accent-ink); -webkit-text-stroke: 0; text-shadow: none; border-radius: 10px; padding: 0 14px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1080" data-height="1920">
      <div id="bg" class="clip" data-start="0" data-duration="{total}" data-track-index="0"></div>
      <div id="cam">
        <video id="aroll" class="clip" src="{a.aroll}" data-start="0" data-media-start="0" data-duration="{total}" data-has-audio="true" data-track-index="1" playsinline></video>
{hero_html}
      </div>
{chr(10).join(broll_html)}
      <div id="captions" data-composition-src="compositions/components/caption-highlight.html" data-composition-id="caption-highlight" data-start="0" data-duration="{total}" data-track-index="10"></div>
{chr(10).join(chap_html)}
{lt_html}
      <div id="hook" class="clip" data-start="0" data-duration="{round(hook_end, 3)}" data-track-index="13"><div class="hf-catalog-focus-blur-resolve">{hook_words}</div></div>
{sfx_html}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      tl.set("#cam", {{ scale: 1 }}, 0);
      // camera: slow zoom per take, punch-ins and scale-out settles on chosen cuts
      {(chr(10) + '      ').join(cam)}
      // hook: focus-blur-resolve (house values), phrase scales as one unit
      tl.fromTo(".hf-catalog-focus-blur-resolve span", {{ opacity: {HK["from"]["opacity"]}, "--hf-word-blur": "{HK["from"]["blurPx"]}px" }}, {{ opacity: 1, "--hf-word-blur": "0px", duration: {HK["durationSec"]}, ease: "{HK["ease"]}" }}, 0);
      tl.fromTo(".hf-catalog-focus-blur-resolve", {{ scale: {HK["from"]["scale"]} }}, {{ scale: 1, duration: {HK["durationSec"]}, ease: "{HK["ease"]}" }}, 0);
      {(chr(10) + '      ').join(broll_js)}
      {(chr(10) + '      ').join(chap_js)}
      {hero_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
(proj / "index.html").write_text(index)
print(f"{proj/'index.html'}  total {total}s, {len(groups)} caption groups, {sum(w['key'] for w in words)} key words, {len(sfx)} sfx")
