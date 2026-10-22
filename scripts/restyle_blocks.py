#!/usr/bin/env python3
"""Restyle installed HyperFrames catalog items to the OVS house style.

Usage: restyle_blocks.py PROJECT_DIR
Idempotent: files already carrying the OVS marker are skipped.

General pass on every block/component:
  - 1920x1080 canvases become 1080x1920 (portrait)
  - display faces -> Inter 900, mono/body faces -> Inter 700 (Caveat kept for hw-* handwriting)
  - saturated accent colours -> style.json colors.accent (#FFD400)
  - injects the house tokens (+ Archivo width-125 @font-face) as the first <style>
Per-block layout fixes (safe zone, caption y, sizes) are in FIXES below.
"""
import colorsys, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STYLE = json.loads((ROOT / "style.json").read_text())
ACCENT = STYLE["colors"]["accent"]
MARK = "<!-- ovs-house-style -->"

TOKENS = f"""{MARK}
    <style>
      @font-face {{
        font-family: "Archivo";
        src: url("assets/fonts/Archivo-Variable.ttf") format("truetype");
        font-weight: 100 900;
        font-stretch: 62% 125%;
        font-display: block;
      }}
      :root {{
        --ovs-accent: {ACCENT};
        --ovs-accent-ink: {STYLE["colors"]["accentInk"]};
        --ovs-font-caption: "Inter", "Arial Black", sans-serif;
        --ovs-font-heading: "{STYLE["fonts"]["heading"]["family"]}", "Arial Black", sans-serif;
        --ovs-heading-stretch: {STYLE["fonts"]["heading"]["width"]}%;
        --font-display: var(--ovs-font-caption);
        --font-body: var(--ovs-font-caption);
        --font-mono: var(--ovs-font-caption);
        --accent: var(--ovs-accent);
        --hw-font-print: var(--ovs-font-caption);
        --hw-ink-accent: var(--ovs-accent);
      }}
    </style>
"""

DISPLAY = ["League Gothic", "Anton", "Oswald", "Archivo Black", "Montserrat", "Bebas Neue", "Outfit",
           "Poppins", "Instrument Serif", "Playfair Display", "Barlow Condensed", "Space Grotesk", "Sora"]
MONO = ["Space Mono", "IBM Plex Mono", "JetBrains Mono", "Source Code Pro", "DM Mono"]
BODY = ["Lato", "Roboto", "Open Sans", "Nunito", "IBM Plex Sans", "DM Sans"]  # weight kept
KEEP_COLOURS = {"chromatic-radial-split", "cinematic-zoom", "flash-through-white", "glitch"}  # demo scene fills only


def saturated(hexv):
    x = hexv[1:]
    x = "".join(c * 2 for c in x) if len(x) == 3 else x
    r, g, b = (int(x[i:i + 2], 16) / 255 for i in (0, 2, 4))
    _, l, s = colorsys.rgb_to_hls(r, g, b)
    return s > 0.35 and 0.15 < l < 0.9


def restyle(path: pathlib.Path):
    s = path.read_text()
    if MARK in s:
        return "skip"
    name = path.stem

    # Portrait canvas.
    s = s.replace('data-width="1920"', 'data-width="__W__"').replace('data-height="1080"', 'data-height="1920"').replace('data-width="__W__"', 'data-width="1080"')
    s = re.sub(r"(\b(?:width|max-width)\s*:\s*)1920px", r"\g<1>1080px", s)
    s = re.sub(r"(\b(?:height|max-height)\s*:\s*)1080px", r"\g<1>1920px", s)

    # Faces: display -> Inter 900, mono -> Inter 700. Weight follows the face inside the same rule.
    def fix_rule(m):
        body = m.group(0)
        fam = re.search(r"font-family\s*:\s*([^;]+);", body)
        if not fam:
            return body
        f = fam.group(1)
        if any(d in f for d in DISPLAY):
            body = body.replace(fam.group(0), "font-family: var(--ovs-font-caption);")
            body = re.sub(r"font-weight\s*:\s*[^;]+;", "font-weight: 900;", body) if "font-weight" in body else body.replace("font-family: var(--ovs-font-caption);", "font-family: var(--ovs-font-caption);\n        font-weight: 900;")
        elif any(d in f for d in MONO):
            body = body.replace(fam.group(0), "font-family: var(--ovs-font-caption);")
            body = re.sub(r"font-weight\s*:\s*[^;]+;", "font-weight: 700;", body)
        return body
    s = re.sub(r"\{[^{}]*\}", fix_rule, s)
    # JS canvas measuring and inline font strings.
    for d in DISPLAY:
        s = s.replace(f'"{d}"', '"Inter"').replace(f"'{d}'", "'Inter'")
    for d in MONO + BODY:
        s = s.replace(f'"{d}"', '"Inter"').replace(f"'{d}'", "'Inter'")

    # Accent colours.
    if name not in KEEP_COLOURS:
        s = re.sub(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", lambda m: ACCENT if saturated(m.group(0)) else m.group(0), s)
        s = re.sub(r"rgba?\((\d+),\s*(\d+),\s*(\d+)",
                   lambda m: "rgba(255, 212, 0" if max(map(int, m.groups())) - min(map(int, m.groups())) > 80 else m.group(0), s)

    # Inter is bundled with HyperFrames and Caveat ships as a local file: drop remote Google Fonts links.
    s = re.sub(r"\s*<link[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>", "", s, flags=re.S)
    s = re.sub(r"\s*@import url\([\"']https://fonts\.googleapis\.com[^)]*\);", "", s)

    # Tokens go first in <head> (components without <head> get them at the top).
    s = s.replace("<head>", "<head>\n    " + TOKENS, 1) if "<head>" in s else TOKENS + s
    s = viewport(FIXES.get(name, lambda t: t)(s))
    path.write_text(s)
    return "ok"


def sub(pattern, repl, count=0, flags=re.S):
    return lambda t: re.sub(pattern, repl, t, count=count, flags=flags)


def chain(*fns):
    def run(t):
        for f in fns:
            t = f(t)
        return t
    return run


SAFE = STYLE["safeZone"]
CAP = STYLE["captions"]
# Lower thirds: left edge at the safe-zone x, sitting just above the safe-zone floor (y 1260).
LT = chain(
    sub(r"(#root \.lt \{[^}]*?)bottom:\s*\d+px;", rf"\1top: auto;\n        bottom: {1920 - SAFE['yMax'] + 20}px;", 1),
    sub(r"(#root \.lt \{[^}]*?)left:\s*\d+px;", rf"\1left: {SAFE['xMin']}px;\n        max-width: {SAFE['xMax'] - SAFE['xMin']}px;", 1),
)
FIXES = {n: LT for n in ["lt-accent-underline", "lt-bold-block", "lt-clean-bar", "lt-color-block", "lt-dark-card",
                         "lt-kicker-name", "lt-mask-reveal", "lt-neon-border", "lt-side-rule", "lt-soft-pill", "lt-stack-bars"]}
# Lower-third names in Inter Black.
LT_NAME = sub(r"(\.(?:lt|nb)-name \{[^}]*?)font-weight:\s*\d+;", r"\1font-weight: 900;", 1)
for _n in [k for k in FIXES if k.startswith("lt-")]:
    FIXES[_n] = chain(FIXES[_n], LT_NAME)
# lt-neon-border has its own wrapper: same anchor as the other lower thirds.
FIXES["lt-neon-border"] = chain(
    sub(r"(#root \.nb-wrap \{[^}]*?)left:\s*\d+px;\s*bottom:\s*\d+px;", rf"\1left: {SAFE['xMin'] - 120}px;\n        bottom: {1920 - SAFE['yMax'] - 130}px;", 1),
    LT_NAME)
# Text on a solid accent block reads black.
FIXES["lt-color-block"] = chain(LT, sub(r"(#root \.lt-name \{[^}]*?)color:\s*#ffffff;", r"\1color: var(--ovs-accent-ink);", 1),
                                sub(r"(#root \.lt-role \{[^}]*?)color:\s*rgba\(255, 255, 255, 0\.86\);", r"\1color: rgba(0, 0, 0, 0.78);", 1),
                                sub(r"(#root \.lt-block \{[^}]*?)padding:", r"\1border-radius: 10px;\n        padding:", 1))
# Default captions (caption-highlight): white Inter 900, centred at y≈1190, accent block only on key words.
FIXES["caption-highlight"] = chain(
    sub(r"(\.hl-group \{[^}]*?)bottom:\s*\d+px;", rf"\1top: {CAP['centerY']}px;\n        transform: translateY(-50%);", 1),
    sub(r"(\.hl-group \{[^}]*?)padding:\s*0 100px;", rf"\1padding: 0 {SAFE['xMin']}px;", 1),
    sub(r"(\.hl-group \{[^}]*?)align-items:\s*flex-end;", r"\1align-items: center;", 1),
    sub(r"(\.hl-word \{[^}]*?)font-size:\s*\d+px;", rf"\1font-size: {CAP['sizePx']}px;", 1),
    sub(r"(\.hl-word \{[^}]*?)text-shadow:[^;]+;", rf"\1-webkit-text-stroke: {CAP['strokePx']}px {CAP['strokeColor']};\n        paint-order: stroke fill;\n        text-shadow: {CAP['shadow']};", 1),
    sub(r'fitFontSize\(groupText, 80, "800", "Inter", 1620\)', f'fitFontSize(groupText, {CAP["sizePx"]}, "900", "Inter", {SAFE["xMax"] - SAFE["xMin"]})'),
)
# Karaoke option: same position and width limits as the default captions.
FIXES["caption-pill-karaoke"] = chain(
    sub(r"(\.safe-zone \{[^}]*?)bottom:\s*\d+px;", rf"\1top: {CAP['centerY'] - 110}px;", 1),
    lambda t: t.replace("1600px", f"{SAFE['xMax'] - SAFE['xMin']}px").replace("1600,", f"{SAFE['xMax'] - SAFE['xMin']},"),
)
FIXES["caption-pill-karaoke"] = chain(FIXES["caption-pill-karaoke"],
                                     sub(r"(\.caption-copy \{[^}]*?)font-size:", r"\1text-transform: uppercase;\n        font-size:", 1),
                                     lambda t: t.replace('var FONT_WEIGHT = "700";', 'var FONT_WEIGHT = "900";')
                                                .replace("var FONT_WIDTH_SAFETY = 1.18;", "var FONT_WIDTH_SAFETY = 1.32;")
                                                .replace("word.text.toLowerCase()", "word.text.toUpperCase()")
                                                .replace("w.text.toLowerCase()", "w.text.toUpperCase()"),
                                     sub(r"\s*<link[^>]*family=Poppins[^>]*/>", "", 1))
# Default captions: the accent block only appears on words flagged {key: true}; other words stay white, no box.
POP = STYLE["captions"]["popIn"]
FIXES["caption-highlight"] = chain(
    FIXES["caption-highlight"],
    # centre each group on y≈1190 without a transform (GSAP owns transform for the pop)
    lambda t: t.replace(f"top: {CAP['centerY']}px;\n        transform: translateY(-50%);",
                        f"top: {CAP['centerY'] - 60}px;\n        height: 120px;"),
    # key words: accent block + black text for the whole time their group is on screen
    sub(r"tl\.to\(bgEl, \{ opacity: 1, scaleX: 1, duration: 0\.15, ease: \"power2\.out\" \}, w\.start\);",
        'if (w.key) tl.set(bgEl, { opacity: 1, scaleX: 1 }, g.start);', 1),
    sub(r"tl\.to\(bgEl, \{ opacity: 0, scaleX: 1\.02, duration: 0\.1, ease: \"power2\.in\" \}, w\.end\);\s*tl\.set\(bgEl, \{ scaleX: 0 \}, w\.end \+ 0\.1\);", "", 1),
    sub(r'(wordEl\.id = "hl-w-" \+ wi;)', r'\1\n            if (w.key) wordEl.className += " hl-key";', 1),
    sub(r"(\.hl-word-bg \{[^}]*?)background:[^;]+;", r"\1background: var(--ovs-accent);", 1),
    sub(r"(\.hl-word-bg \{[^}]*?)box-shadow:[^;]+;", r"\1box-shadow: none;", 1),
    lambda t: t.replace("</style>", "  .hl-key { -webkit-text-stroke: 0; text-shadow: none; }\n      .hl-key .hl-word-text { color: var(--ovs-accent-ink); }\n    </style>", 1),
    # pop-in per group: 0.14s back.out
    sub(r"\{ opacity: 0 \},\s*\{ opacity: 1, duration: 0\.12, ease: \"power2\.out\" \},",
        f'{{ opacity: 0, scale: 0.6 }},\n            {{ opacity: 1, scale: 1, duration: {POP["durationSec"]}, ease: "back.out(2)" }},', 1),
)
# Text behind subject: one hero word in the heading face, fit to 92% of frame width around y 620;
# front captions use the caption face/size, no italics.
HERO = round(1080 * STYLE["textBehindSubject"]["fitWidthPct"] / 100)
FIXES["caption-parallax-layers"] = chain(
    # request the heading face from the first frame so document.fonts.ready waits for it
    lambda t: t.replace('<div id="behind-stage"', '<div aria-hidden="true" style="position:absolute;opacity:0;font-family:var(--ovs-font-heading);font-stretch:125%;font-weight:900">A</div>\n      <div id="behind-stage"', 1),
    sub(r"(\.behind-safe-zone \{[^}]*?)top:\s*\d+px;", r"\1top: 470px;", 1),
    # shrink-wrapping to half the frame made scrollWidth miss the left overflow, so the fit overshot
    sub(r"(\.caption-block \{[^}]*?)top:\s*0;", r"\1top: 0;\n        width: max-content;", 1),
    # measure the word spans themselves, and refit once the heading face has actually loaded
    lambda t: t.replace("var natW = line.scrollWidth;",
                        "var natW = 0;\n              line.querySelectorAll('.word').forEach(function (el, i) { natW += el.offsetWidth + (i ? 14 : 0); });")
               .replace("document.fonts.ready.then(function () {\n        applyBehindScales();",
                        "Promise.all([document.fonts.ready, document.fonts.load('900 220px Archivo')]).then(function () {\n        applyBehindScales();")
               # the renderer can capture before that promise settles: refit on every seek too (layout-only, seek-safe)
               .replace('window.__timelines["caption-parallax-layers"] = tl;',
                        'tl.eventCallback("onUpdate", applyBehindScales);\n      window.__timelines["caption-parallax-layers"] = tl;'),
    # house motion on the hero word: scale 1.18 -> 1 over 0.35s, then a slow 4% drift until the block ends
    lambda t: t.replace(
        'tl.to(wordEl, { opacity: 1, duration: ENTRY_DUR, ease: "power2.out" }, wordStart);',
        'tl.to(wordEl, { opacity: 1, duration: ENTRY_DUR, ease: "power2.out" }, wordStart);\n'
        f'            tl.fromTo(wordEl, {{ scale: {STYLE["textBehindSubject"]["in"]["scaleFrom"]} }}, {{ scale: 1, duration: {STYLE["textBehindSubject"]["in"]["durationSec"]}, ease: "power3.out" }}, wordStart);\n'
        # fromTo with explicit start: a plain .to() would record 1.18 as its start when a seek skips the entrance
        f'            tl.fromTo(wordEl, {{ scale: 1 }}, {{ immediateRender: false, scale: {1 + STYLE["textBehindSubject"]["drift"]["scale"]}, duration: Math.max(0.1, nextStart - wordStart - {STYLE["textBehindSubject"]["in"]["durationSec"]}), ease: "none" }}, wordStart + {STYLE["textBehindSubject"]["in"]["durationSec"]});', 1),
    sub(r"(\.front-safe-zone \{[^}]*?)top:\s*\d+px;", rf"\1top: {CAP['centerY'] - 150}px;", 1),
    lambda t: t.replace("var BEHIND_WIDTH = 1800;", f"var BEHIND_WIDTH = {HERO};")
               .replace("var FRONT_WIDTH = 1750;", f"var FRONT_WIDTH = {SAFE['xMax'] - SAFE['xMin']};")
               .replace('fitFontSize(behindText, 220, "400", "Inter", BEHIND_WIDTH)', 'fitFontSize(behindText, 220, "900", "Archivo", BEHIND_WIDTH)')
               .replace('fitFontSize(frontText, 130, "400", "Inter", FRONT_WIDTH)', f'fitFontSize(frontText, {CAP["sizePx"]}, "900", "Inter", FRONT_WIDTH)')
               .replace("scaleY(2.8)", "scaleY(1.4)")
               .replace("font-style: italic;", "font-style: normal;"),
    sub(r"(\.word--behind \{[^}]*?)font-family:[^;]+;", r"\1font-family: var(--ovs-font-heading);\n        font-stretch: var(--ovs-heading-stretch);\n        text-transform: uppercase;", 1),
    sub(r"(\.word--behind \{[^}]*?)text-shadow:[^;]+;", r"\1text-shadow: none;", 1),
    sub(r"(\.word--front-(?:normal|italic) \{[^}]*?)font-size:\s*130px;", rf"\1font-size: {CAP['sizePx']}px;\n        text-transform: uppercase;"),
)
# Handwritten titles: centre on the portrait canvas and shrink to the safe-zone width.
HW_FIT = (f"var rect = line.getBoundingClientRect();\n        if (rect.width > {SAFE['xMax'] - SAFE['xMin']}) {{ line.style.fontSize = "
          f"Math.floor(CONFIG.fontSize * {SAFE['xMax'] - SAFE['xMin']} / rect.width) + \"px\"; rect = line.getBoundingClientRect(); }}")
FIXES["hw-title"] = lambda t: (t.replace("var rect = line.getBoundingClientRect();", HW_FIT, 1)
                               .replace("(1920 - rect.width) / 2", "(1080 - rect.width) / 2")
                               .replace("(1080 - rect.height) / 2", "(1920 - rect.height) / 2")
                               .replace("fontSize: 120,", "fontSize: 110,"))
FIXES["hw-write-title"] = lambda t: (t.replace("(1920 - wPx) / 2", "(1080 - wPx) / 2")
                                     .replace("(1080 - hPx) / 2", "(1920 - hPx) / 2")
                                     .replace("fontSize: 170,", "fontSize: 130,"))
# Logo outro (≤2s CTA use only): re-centre for portrait, tagline in the caption face, URL in an accent pill.
FIXES["logo-outro"] = chain(
    lambda t: t.replace("left: 880px;\n          top: 380px;", "left: 460px;\n          top: 700px;")
               .replace("left: 760px;\n          top: 300px;", "left: 340px;\n          top: 620px;")
               .replace("top: 720px;", "top: 1040px;")
               .replace("{ x: 1920, opacity: 0 }", "{ x: 1080, opacity: 0 }")
               .replace('content="width=1920, height=1080"', 'content="width=1080, height=1920"'),
    sub(r"(\.tagline \{[^}]*?)font-size:\s*44px;\s*font-weight:\s*500;", r"\1font-size: 56px;\n          font-weight: 900;\n          text-transform: uppercase;\n          max-width: 840px;", 1),
    sub(r"(\.url-pill \{[^}]*?)background:[^;]+;\s*border:[^;]+;\s*border-radius:\s*100px;", r"\1background: var(--ovs-accent);\n          border: 0;\n          border-radius: 10px;", 1),
    sub(r"(\.url-text \{[^}]*?)font-size:\s*18px;\s*color:[^;]+;", r"\1font-size: 28px;\n          font-weight: 900;\n          color: var(--ovs-accent-ink);", 1),
)


def viewport(t):
    return t.replace('content="width=1920, height=1080"', 'content="width=1080, height=1920"')
# Kinetic slam: fit each word inside the safe-zone width.
FIXES["caption-kinetic-slam"] = lambda t: t.replace('fitFontSize(w.text.toUpperCase(), 220, "400", "\'Inter\', sans-serif", 1720)',
                                                    f'fitFontSize(w.text.toUpperCase(), 220, "900", "\'Inter\', sans-serif", {round((SAFE["xMax"] - SAFE["xMin"]) * 0.85)})')  # 0.04em tracking isn't measured
# CTA close: caption face, caps.
# Caps Inter Black advances ~0.66em, not the 0.47em the size estimate assumes; target the safe-zone width (78%).
FIXES["cta-close"] = lambda t: (re.sub(r"font-weight:\s*600;", "font-weight: 900;\n            text-transform: uppercase;", t)
                                .replace("min(10.4cqw, 30cqh)", "min(7.4cqw, 30cqh)")
                                .replace("76 / (actionCharacters * 0.47)", "78 / (actionCharacters * 0.66)"))
# Hook reveal: house values (style.json hook.text) in the size table and the timeline integration snippet.
HOOK = STYLE["hook"]["text"]
FIXES["focus-blur-resolve"] = lambda t: (t.replace('pick(tones, vars.tone, "ink")', 'pick(tones, vars.tone, "paper")')
    .replace('"default": "ink"', '"default": "paper"')
    .replace('paper: "#fafafa"', 'paper: "#ffffff"')
    .replace('var sizes = { compact: "40px", standard: "56px", display: "84px" };',
                                                   f'var sizes = {{ compact: "56px", standard: "{CAP["sizePx"]}px", display: "120px" }};')
    .replace("{ opacity: 0, '--hf-word-scale': 1.08, '--hf-word-blur': '16px' }, { opacity: 1, '--hf-word-scale': 1, '--hf-word-blur': '0px', duration: 0.52, stagger: 0.05, ease: 'power3.out' }",
             # scale the phrase as one unit (per-word scale makes neighbours collide); blur + opacity per word
             f"{{ opacity: {HOOK['from']['opacity']}, '--hf-word-blur': '{HOOK['from']['blurPx']}px' }}, "
             f"{{ opacity: 1, '--hf-word-blur': '0px', duration: {HOOK['durationSec']}, stagger: 0, ease: '{HOOK['ease']}' }}, startTime);\n"
             f"  tl.fromTo('.hf-catalog-focus-blur-resolve', {{ scale: {HOOK['from']['scale']} }}, "
             f"{{ scale: 1, duration: {HOOK['durationSec']}, ease: '{HOOK['ease']}' }}")
    .replace("startTime);\n  tl.fromTo('.hf-catalog-focus-blur-resolve', { scale", "startTime);\n  tl.fromTo('.hf-catalog-focus-blur-resolve', { scale"))
FIXES["mk-emphasis-type"] = sub(r"--mk-font:[^;]+;", "--mk-font: var(--ovs-font-heading);\n        font-stretch: var(--ovs-heading-stretch);", 1)


if __name__ == "__main__":
    proj = pathlib.Path(sys.argv[1])
    for f in sorted(proj.glob("compositions/*.html")) + sorted(proj.glob("compositions/components/*.html")):
        print(f"{restyle(f):4} {f.relative_to(proj)}")
