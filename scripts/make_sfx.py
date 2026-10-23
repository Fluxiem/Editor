#!/usr/bin/env python3
"""Synthesize the kit sound palette: hit (hook), tap (each list item / notification), chime (close).

Usage: make_sfx.py [--out templates/ovs-vertical/assets/sfx] [--names hit tap chime]

Pure numpy, no samples, so the files are ours to use anywhere. Each file is 48 kHz, 16-bit,
stereo (same as pop.wav / whoosh.wav), normalised to a -3 dBFS peak with a short fade at the
tail so nothing clicks. Seeded, so a re-run writes the same bytes.

  hit    0.42 s  low thump that drops from 160 to 50 Hz, with a bright click on the front
  tap    0.08 s  soft UI tap: short wooden knock with a little top
  chime  1.20 s  two-note bell (A5 then E6), small left/right spread, long gentle ring

build_comp.py copies templates/ovs-vertical/assets/sfx/ into each project; studio.audio.sfxPalette
"kit" puts hit on the hook, tap on each list item / notification, whoosh on scene changes and
chime at the end. Upload the files to Drive Library/Sounds to make them pickable in the studio.
"""
import argparse, pathlib, wave
import numpy as np

SR = 48000
PEAK_DB = -3.0
ROOT = pathlib.Path(__file__).resolve().parent.parent


def t_axis(sec):
    return np.arange(int(round(sec * SR))) / SR


def env(t, attack, tau):
    """Linear attack, exponential decay."""
    a = np.clip(t / attack, 0, 1) if attack > 0 else np.ones_like(t)
    return a * np.exp(-np.maximum(t - attack, 0) / tau)


def sweep(t, f0, f1, tau):
    """Sine whose pitch falls exponentially from f0 to f1 (time constant tau)."""
    f = f1 + (f0 - f1) * np.exp(-t / tau)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def onepole_lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def fade_tail(x, sec):
    n = int(sec * SR)
    x[-n:] *= np.linspace(1, 0, n) ** 2
    return x


def hit(rng):
    t = t_axis(0.42)
    body = sweep(t, 160, 50, 0.035) * env(t, 0.002, 0.11)
    body = np.tanh(1.8 * body) / np.tanh(1.8)                    # a little warmth / weight
    knock = np.sin(2 * np.pi * 220 * t) * env(t, 0.001, 0.025) * 0.45
    noise = rng.standard_normal(len(t))
    click = np.diff(noise, prepend=0) * env(t, 0.0003, 0.004) * 0.25   # high-passed noise burst
    click += np.sin(2 * np.pi * 3200 * t) * env(t, 0.0003, 0.006) * 0.2
    tail = onepole_lp(noise, 900) * env(t, 0.005, 0.09) * 0.25
    m = fade_tail(body + knock + click + tail, 0.04)
    return np.stack([m, m], 1)


def tap(rng):
    t = t_axis(0.08)
    wood = sweep(t, 720, 560, 0.01) * env(t, 0.0008, 0.016)
    top = np.sin(2 * np.pi * 1850 * t) * env(t, 0.0004, 0.007) * 0.45
    noise = rng.standard_normal(len(t))
    click = onepole_lp(np.diff(noise, prepend=0), 6000) * env(t, 0.0002, 0.0015) * 0.35
    m = fade_tail(wood + top + click, 0.015)
    return np.stack([m, m], 1)


def bell(t, f, tau):
    """Soft bell: fundamental + octave + two quiet inharmonic partials that die faster."""
    parts = [(1.0, 1.0, 1.0), (2.0, 0.32, 0.55), (2.76, 0.12, 0.35), (5.4, 0.05, 0.18)]
    return sum(a * np.sin(2 * np.pi * f * r * t) * env(t, 0.005, tau * k) for r, a, k in parts)


def chime(rng):
    t = t_axis(1.2)
    out = np.zeros((len(t), 2))
    for start, f, pan in ((0.0, 880.0, -0.15), (0.14, 1318.5, 0.15)):   # A5 then E6
        n0 = int(start * SR)
        tt = t[: len(t) - n0]
        note = bell(tt, f, 0.42)
        out[n0:, 0] += note * np.sqrt((1 - pan) / 2)
        out[n0:, 1] += note * np.sqrt((1 + pan) / 2)
    out[:, 0] = fade_tail(out[:, 0], 0.25); out[:, 1] = fade_tail(out[:, 1], 0.25)
    return out


def write(path, x):
    x = x / np.max(np.abs(x)) * 10 ** (PEAK_DB / 20)
    pcm = np.round(x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


SOUNDS = {"hit": hit, "tap": tap, "chime": chime}
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(ROOT / "templates/ovs-vertical/assets/sfx"))
ap.add_argument("--names", nargs="+", choices=SOUNDS, default=list(SOUNDS))
a = ap.parse_args()
out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
for name in a.names:
    x = SOUNDS[name](np.random.default_rng(list(SOUNDS).index(name) + 7))
    write(out / f"{name}.wav", x)
    print(f"{name}.wav  {len(x) / SR:.2f}s -> {out / (name + '.wav')}")
