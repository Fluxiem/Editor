#!/usr/bin/env python3
"""Generate the starter pack of transition overlays: VP9 WebM with alpha + a sidecar JSON each.

Usage: make_overlays.py [--out library/Transitions] [--names flash-soft ...] [--size 1080x1920]
                        [--preview DIR [--bg FRAME.jpg]]

Each overlay is 30 fps, 10-24 frames, yuva420p (straight alpha: RGB is the light's colour,
alpha its strength), drawn with numpy and encoded with libvpx-vp9 (-auto-alt-ref 0 keeps the
alpha). Next to it, <name>.json says how to place it on a cut:
  {"markFrame": N, "blend": "screen"|"normal"|"lighten", "frames": total}
markFrame is the overlay frame that lands on the cut, so the clip starts markFrame/30 s early.
studio.transitions.list items with look "overlay" name the file; files dropped in Drive
Library/Transitions work the same way (sidecar optional).

  flash-soft        12 f  white bloom from the centre, peaks on the cut           screen
  light-leak-warm   24 f  peach / pink leak sweeping left to right               screen
  light-leak-lilac  24 f  lilac / pink leak sweeping right to left               screen
  film-burn         20 f  amber burn eating in from the right edge, blows out    screen
  whip-streak       10 f  horizontal motion streaks, left to right                screen

Everything is seeded, so a re-run gives the same frames. --preview writes a contact sheet per
overlay (decoded back from the WebM, blended over dark grey and over --bg) to check the look.
"""
import argparse, json, pathlib, shutil, subprocess, tempfile
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
FPS = 30


# ---- helpers -----------------------------------------------------------------------------------
def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def resize(a, w, h):
    """Bicubic resize of a float HxW array (or HxWxC)."""
    if a.ndim == 3:
        return np.stack([resize(a[..., c], w, h) for c in range(a.shape[2])], -1)
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((w, h), Image.BICUBIC))


def box(a, r, axis):
    """Box blur of radius r along axis (cumulative sum, edge-clamped)."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim; pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur(a, r, axis):
    """Near-gaussian blur: three box passes."""
    for _ in range(3):
        a = box(a, max(1, int(r / 1.7)), axis)
    return a


def fbm(rng, w, h, octaves=4, base=4, persistence=0.55):
    """Fractal value noise in [-1, 1], h x w."""
    out = np.zeros((h, w), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        cw, ch = base * 2 ** o + 1, int((base * 2 ** o) * h / w) + 2
        out += amp * resize(rng.uniform(-1, 1, (ch, cw)).astype(np.float32), w, h)
        tot += amp; amp *= persistence
    return out / tot


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def light_to_rgba(L, gain=1.0):
    """Linear light (H x W x 3, >= 0) -> straight-alpha RGBA in 0..1: tone-mapped so hot cores go white,
    alpha = brightest channel, colour = tone-mapped light / alpha."""
    out = 1 - np.exp(-L * gain)
    a = out.max(-1)
    rgb = np.where(a[..., None] > 1e-4, out / np.maximum(a[..., None], 1e-4), 1.0)
    return np.concatenate([np.clip(rgb, 0, 1), a[..., None]], -1)


def env_peak(f, frames, mark, rise=2.0, fall=1.6):
    """Near 0 on the first frame -> 1 on the mark -> exactly 0 on the last frame; eased."""
    if f <= mark:
        return ((f + 1) / (mark + 1)) ** rise
    return max(0.0, 1 - (f - mark) / (frames - 1 - mark)) ** fall


# ---- overlays ----------------------------------------------------------------------------------
def flash_soft(W, H, rng):
    frames, mark = 12, 5
    curve = [0.04, 0.1, 0.2, 0.38, 0.66, 1.0, 0.74, 0.5, 0.31, 0.16, 0.06, 0.0]
    w, h = W // 4, H // 4
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(x / w - 0.5, (y / h - 0.44) * h / w)                       # bloom a little above centre
    tint = hexrgb("#FFF8F1")
    for f in range(frames):
        i = curve[f]
        core = np.exp(-(r / (0.18 + 0.9 * i)) ** 2)                          # bloom opens up as it brightens
        a = np.clip(i ** 0.85 * (core + (1 - core) * i ** 2.5) * (1.1 - 0.12 * r), 0, 1)
        yield np.concatenate([np.broadcast_to(tint, (H, W, 3)), resize(a, W, H)[..., None]], -1)


def leak(W, H, rng, cols, direction, frames=24, mark=11):
    """Light leak: tall soft bands of light in the palette sweep across the frame, brightest (white-hot
    core, saturated fringe) on the mark, with faint streaks running along the bands like a film gate."""
    w, h = W // 6, H // 6
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x /= w; y /= w                                                           # units of frame width
    hn = h / w
    sat = [c ** 2.6 for c in cols]                                           # saturated fringe, white core
    bands = [  # colour, half-width, half-height, tilt, y centre, lag, amplitude
        (sat[0], 0.17, 1.9, 0.22, hn * 0.45, 0.0, 1.9),
        (sat[1], 0.09, 0.75, 0.30, hn * rng.uniform(0.2, 0.4), -0.10, 1.1),
        (sat[2], 0.26, 0.55, 0.12, hn * rng.uniform(0.6, 0.85), 0.08, 0.9),
        (cols[1] ** 1.5, 0.75, 2.2, 0.15, hn * 0.5, 0.03, 0.35),            # soft wash around the front
    ]
    stripes = [resize(rng.uniform(-1, 1, (1, 40)).astype(np.float32), 800, 1)[0] for _ in bands]
    for f in range(frames):
        u = f / (frames - 1)
        e = env_peak(f, frames, mark, rise=1.6, fall=1.3)
        L = np.zeros((h, w, 3), np.float32)
        for (c, sx, sy, tilt, y0, lag, amp), st in zip(bands, stripes):
            p = np.clip(u + lag, 0, 1)
            px = -0.45 + 1.9 * (p * p * (3 - 2 * p) * 0.6 + p * 0.4)          # off one edge to off the other
            if direction < 0:
                px, tilt = 1 - px, -tilt
            ca, sa = np.cos(tilt), np.sin(tilt)
            dx, dy = x - px, y - y0
            rx, ry = (ca * dx + sa * dy) / sx, (-sa * dx + ca * dy) / sy
            g = np.exp(-(rx * rx + ry * ry))
            streak = 1 + 0.3 * st[np.clip(((rx + 4) * 100).astype(int), 0, 799)]
            L += (amp * g * streak)[..., None] * c
        yield resize(light_to_rgba(L * e, gain=1.5), W, H)


def light_leak_warm(W, H, rng):
    yield from leak(W, H, rng, [hexrgb("#FFDCCB"), hexrgb("#F6BDD8"), hexrgb("#FFC9A8")], +1)


def light_leak_lilac(W, H, rng):
    yield from leak(W, H, rng, [hexrgb("#C9B9FF"), hexrgb("#F6BDD8"), hexrgb("#B7A6FF")], -1)


def film_burn(W, H, rng):
    frames, mark = 20, 9
    w, h = W // 3, H // 3
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    xn, yn = x / w, y / h
    d = (1 - xn) * 1.0 + 0.18 * (yn - 0.42) ** 2                             # distance from the right edge
    n1, n2 = fbm(rng, w, h, 5, 3), fbm(rng, w, h, 5, 3)
    ramp_t = np.array([0.0, 0.08, 0.22, 0.42, 0.65, 0.85, 1.0], np.float32)
    ramp_c = np.array([hexrgb(c) for c in ("#3A0500", "#8A1A00", "#E04A00", "#FF8A12", "#FFC24A", "#FFE6A8", "#FFF8EA")])
    ramp_a = np.array([0.0, 0.55, 0.85, 0.97, 1.0, 1.0, 1.0], np.float32)
    for f in range(frames):
        u = f / (frames - 1)
        n = n1 * (1 - u) + n2 * u
        if f <= mark:
            front = -0.22 + 1.59 * (f / mark) ** 1.4                         # clear on frame 0, covers the frame on the mark
            fade = 1.0
        else:
            k = (f - mark) / (frames - 1 - mark)
            front = 1.37 - 1.2 * k ** 0.8                                    # recedes to the edge
            fade = (1 - k) ** 1.2
        heat = np.clip((front - d + 0.3 * n) / 0.55, 0, 1) * (0.45 + 0.55 * fade)   # cools as it dies
        c = np.stack([np.interp(heat, ramp_t, ramp_c[:, i]) for i in range(3)], -1)
        a = np.interp(heat, ramp_t, ramp_a) * fade
        rgba = np.concatenate([c, a[..., None]], -1).astype(np.float32)
        yield resize(rgba, W, H)


def whip_streak(W, H, rng):
    frames, mark = 10, 4
    w = W // 4                                                               # streaks are smooth along x
    streaks = []
    for _ in range(260):
        streaks.append(dict(y=rng.uniform(0, H), th=rng.choice([1.2, 2, 3, 5, 9, 16, 30]) * rng.uniform(0.7, 1.3),
                            x=rng.uniform(-1.6, 0.4), ln=rng.uniform(0.6, 1.6), v=rng.uniform(0.3, 0.7),
                            b=rng.uniform(0.15, 1.0) ** 1.5, warm=rng.uniform(-1, 1), t=rng.uniform(0, 1)))
    xs = (np.arange(w, dtype=np.float32) / w)[None, :]
    for f in range(frames):
        e = env_peak(f, frames, mark, rise=1.5, fall=1.4)
        L = np.zeros((H, w, 3), np.float32)
        for s in streaks:
            if s["t"] > 0.2 + 0.8 * e:                                       # more streaks near the mark
                continue
            x0 = s["x"] + s["v"] * (f - mark) / 2
            y0, y1 = int(max(0, s["y"] - 3 * s["th"])), int(min(H, s["y"] + 3 * s["th"] + 1))
            if y1 <= y0:
                continue
            ys = np.arange(y0, y1, dtype=np.float32)[:, None]
            prof = np.exp(-((ys - s["y"]) / s["th"]) ** 2)                   # vertical profile
            along = smoothstep(x0, x0 + 0.3, xs) * (1 - smoothstep(x0 + s["ln"] - 0.35, x0 + s["ln"], xs))
            col = np.array([1.0, 0.97 - 0.03 * s["warm"], 0.94 - 0.08 * s["warm"]], np.float32)
            L[y0:y1] += (s["b"] * prof * along)[..., None] * col
        L = blur(L, 12, 1)
        haze = (0.2 + 0.8 * xs) * 0.55 * e ** 2                              # leading side brighter
        L = L * e * 1.5 + haze[..., None]
        yield resize(light_to_rgba(L, gain=1.2), W, H)


OVERLAYS = {  # name: (generator, markFrame, blend, frames)
    "flash-soft": (flash_soft, 5, "screen", 12),
    "light-leak-warm": (light_leak_warm, 11, "screen", 24),
    "light-leak-lilac": (light_leak_lilac, 11, "screen", 24),
    "film-burn": (film_burn, 9, "screen", 20),
    "whip-streak": (whip_streak, 4, "screen", 10),
}


# ---- encode / preview --------------------------------------------------------------------------
def encode(name, gen, W, H, out, seed):
    rng = np.random.default_rng(seed)
    dither = np.random.default_rng(seed + 1000)
    with tempfile.TemporaryDirectory() as tmp:
        n = 0
        for n, rgba in enumerate(gen(W, H, rng)):
            px = rgba * 255 + dither.uniform(-0.5, 0.5, rgba.shape)            # dither so VP9 doesn't band
            Image.fromarray(np.clip(px + 0.5, 0, 255).astype(np.uint8), "RGBA").save(f"{tmp}/{n:03d}.png", compress_level=1)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/%03d.png",
                        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30",
                        "-row-mt", "1", "-deadline", "good", "-cpu-used", "2", "-an", str(out)], check=True)
    return n + 1


def decode(path, W, H):
    r = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(path), "-f", "rawvideo",
                        "-pix_fmt", "rgba", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W, 4).astype(np.float32) / 255


def blend(base, rgba, mode):
    c, a = rgba[..., :3], rgba[..., 3:]
    m = {"screen": 1 - (1 - base) * (1 - c), "lighten": np.maximum(base, c), "normal": c}[mode]
    return base * (1 - a) + m * a


def preview(path, meta, W, H, bgs, out):
    frames = decode(path, W, H)
    picks = sorted(set(np.linspace(0, len(frames) - 1, 8).round().astype(int)) | {meta["markFrame"]})
    tw, th = 180, 320
    sheet = Image.new("RGB", (tw * len(picks), th * len(bgs)), (0, 0, 0))
    for r, bg in enumerate(bgs):
        for c, i in enumerate(picks):
            img = blend(bg, frames[i], meta["blend"])
            im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((tw, th), Image.LANCZOS)
            if i == meta["markFrame"]:
                im.paste((255, 212, 0), (0, 0, tw, 4))
            sheet.paste(im, (c * tw, r * th))
    sheet.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "library" / "Transitions"))
    ap.add_argument("--names", nargs="+", choices=OVERLAYS, default=list(OVERLAYS))
    ap.add_argument("--size", default="1080x1920")
    ap.add_argument("--preview", help="write <name>_sheet.jpg contact sheets here")
    ap.add_argument("--bg", help="a footage frame to preview over (besides dark grey)")
    a = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("make_overlays.py: ffmpeg not found")
    W, H = map(int, a.size.lower().split("x"))
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for name in a.names:
        gen, mark, mode, frames = OVERLAYS[name]
        path = out / f"{name}.webm"
        n = encode(name, gen, W, H, path, seed=list(OVERLAYS).index(name) + 11)
        assert n == frames, (name, n, frames)
        meta = {"markFrame": mark, "blend": mode, "frames": n}
        (out / f"{name}.json").write_text(json.dumps(meta) + "\n")
        print(f"{name}.webm  {n} frames, mark {mark}, {mode}, {path.stat().st_size / 1e6:.2f} MB")
        if a.preview:
            pv = pathlib.Path(a.preview); pv.mkdir(parents=True, exist_ok=True)
            bgs = [np.full((H, W, 3), 0x20 / 255, np.float32)]
            if a.bg:
                bgs.append(np.asarray(Image.open(a.bg).convert("RGB").resize((W, H)), np.float32) / 255)
            preview(path, meta, W, H, bgs, pv / f"{name}_sheet.jpg")
