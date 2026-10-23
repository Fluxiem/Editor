#!/usr/bin/env python3
"""Background music bed for a reel: cut or looped to length, levelled, faded, ducked under the voice.

Usage: music.py TRACK VOICE.mp4 OUT.m4a --duration S [--level -20] [--start 0] [--duck 8]
                [--fade-in 0.5] [--fade-out 1.5] [--no-duck]

OUT is the music bed only (the voice stays in the A-roll): exactly S seconds of AAC, 48 kHz
stereo. The composition plays it next to the A-roll:
  <audio id="music" class="clip" src="assets/music.m4a" data-start="0" data-duration="S" data-volume="1">

TRACK is a path, or a file name in library/Music/. It is read from --start seconds; when it runs
out before S it starts again from 0 (stream loop, sample-counted so the length is exact).

Levels follow studio.audio.musicLevel, "music under voice": --level is how far the bed sits
under the voice while someone is speaking (dB, -30..-10; the A-roll voice is about -14 LUFS, so
-20 puts the bed near -34 LUFS under speech). With ducking on, the gaps between sentences and the
tail come up by --duck dB; with --no-duck the bed stays at --level throughout. The voice's
integrated loudness is measured, so the balance holds even if the A-roll is not at -14.

Ducking is ffmpeg sidechaincompress keyed on VOICE (speech band 120 Hz - 4 kHz, RMS detection,
ratio 4, 30 ms attack, 600 ms release: back up in about 0.4 s). The key is calibrated to this
voice from 50 ms RMS frames of VOICE (no transcript needed): it is gated a little above the room
tone and flattened, so every word pulls the bed down by the same amount instead of pumping with
the syllables. The speech frames then calibrate the threshold: render, measure the median gain
reduction over speech, move the threshold until it is within 0.3 dB of --duck. It prints what it
measured: voice loudness, bed loudness and true peak, gain reduction in speech / gaps, recovery.
Reels cut to <= 0.35 s pauses mostly stay ducked; the bed comes up in longer pauses and the tail.
Exit status 2, with a message, when TRACK or VOICE can't be read.
"""
import argparse, json, pathlib, re, subprocess, sys, tempfile
import numpy as np

SR = 48000
HOP = 2400                     # 50 ms analysis frames
RATIO, ATTACK, RELEASE = 4.0, 30, 600
ROOT = pathlib.Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description="Music bed: loop/trim, level, fade, duck under VOICE.")
ap.add_argument("track"); ap.add_argument("voice"); ap.add_argument("out")
ap.add_argument("--duration", type=float, required=True)
ap.add_argument("--level", type=float, default=-20.0, help="dB under the voice while speaking (default -20)")
ap.add_argument("--start", type=float, default=0.0, help="seconds into TRACK to start from")
ap.add_argument("--duck", type=float, default=8.0, help="dB the bed drops under speech, relative to the gaps")
ap.add_argument("--fade-in", type=float, default=0.5); ap.add_argument("--fade-out", type=float, default=1.5)
ap.add_argument("--no-duck", action="store_true")
a = ap.parse_args()


def fail(msg):
    print(f"music.py: {msg}", file=sys.stderr)
    sys.exit(2)


def probe_audio(path):
    """Duration (s) of the first audio stream, or None if there is none / it can't be read."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=codec_name,duration:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr.strip().splitlines()[-1:] or ["unreadable"]
    j = json.loads(r.stdout or "{}")
    if not j.get("streams"):
        return None, ["no audio stream"]
    d = j["streams"][0].get("duration") or j.get("format", {}).get("duration")
    return (float(d) if d not in (None, "N/A") else None), []


def pcm(args, ch):
    """Run ffmpeg writing raw f32le to stdout; return an array of shape (n, ch)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args, "-f", "f32le", "-ac", str(ch), "-ar", str(SR), "-"],
                       capture_output=True)
    if r.returncode:
        fail("ffmpeg failed: " + r.stderr.decode(errors="replace").strip()[-400:])
    return np.frombuffer(r.stdout, np.float32).reshape(-1, ch)


def loudness(path):
    """(integrated LUFS, true peak dBTP) via ebur128."""
    r = subprocess.run(["ffmpeg", "-nostats", "-nostdin", "-i", str(path), "-vn", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", s); p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    f = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")
    return f(i), f(p)


def frame_db(x):
    """RMS level (dBFS) per 50 ms frame, channels averaged."""
    n = len(x) // HOP
    p = (x[: n * HOP].astype(np.float64) ** 2).reshape(n, HOP, -1).mean(axis=(1, 2))
    return 10 * np.log10(p + 1e-12)


# ---- inputs ------------------------------------------------------------------------------------
track = pathlib.Path(a.track)
if not track.exists() and (ROOT / "library" / "Music" / a.track).exists():
    track = ROOT / "library" / "Music" / a.track
if not track.exists():
    fail(f"can't read track {a.track}: no such file (looked in library/Music/ too)")
tdur, err = probe_audio(track)
if tdur is None and err:
    fail(f"can't read track {track}: {err[0]}")
if tdur is None or tdur < 0.05:
    tdur = len(pcm(["-i", str(track), "-vn", "-t", "36000"], 1)) / SR      # no duration header: decode once
    if tdur < 0.05:
        fail(f"can't read track {track}: no audio decoded")
S = a.duration
if S <= 0:
    fail("--duration must be > 0")
start = a.start % tdur if a.start >= tdur else max(0.0, a.start)
if a.start >= tdur:
    print(f"  note: --start {a.start:g}s is past the end of the track ({tdur:.1f}s); using {start:.2f}s")
loops = max(0, int(np.ceil((start + S - tdur) / tdur))) if start + S > tdur else 0
fi, fo = max(0.0, a.fade_in), max(0.0, a.fade_out)
if fi + fo > S:
    fi, fo = fi * S / (fi + fo), fo * S / (fi + fo)

vdur, verr = probe_audio(a.voice)
duck = not a.no_duck and a.duck > 0 and S >= 1.0          # too short to analyse: plain bed
if vdur is None and verr:
    if not pathlib.Path(a.voice).exists():
        fail(f"can't read voice {a.voice}: no such file")
    print(f"  note: {a.voice} has no readable audio ({verr[0]}); no ducking, voice assumed at -14 LUFS")
    duck, vI = False, -14.0
else:
    vI, vTP = loudness(a.voice)
    if not np.isfinite(vI):
        print("  note: voice is silent; no ducking, voice assumed at -14 LUFS"); duck, vI = False, -14.0

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    bed_raw, key = tmp / "bed.wav", tmp / "key.wav"
    n0, n = int(round(start * SR)), int(round(S * SR))
    loop = ["-stream_loop", "-1"] if loops else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *loop, "-i", str(track), "-vn", "-af",
                        f"aresample={SR},aformat=sample_fmts=flt:channel_layouts=stereo,"
                        f"atrim=start_sample={n0}:end_sample={n0 + n},asetpts=N/SR/TB,apad=whole_len={n}",
                        "-t", f"{S + 1:.3f}", "-c:a", "pcm_f32le", str(bed_raw)], capture_output=True, text=True)
    if r.returncode or not bed_raw.exists():
        fail(f"can't read track {track}: {r.stderr.strip()[-300:]}")
    bI, bTP = loudness(bed_raw)
    if not np.isfinite(bI):
        fail(f"track {track} is silent from {start:.2f}s")
    target = vI + a.level + (a.duck if duck else 0.0)       # bed loudness in the gaps
    gain = target - bI
    bed = pcm(["-i", str(bed_raw)], 2)[:n]
    peak = 20 * np.log10(np.max(np.abs(bed)) + 1e-12) + gain
    limiter = f",alimiter=limit={10 ** (-1.5 / 20):.4f}:level=0:attack=2:release=60" if peak > -1.5 else ""
    vol = f"volume={gain:.2f}dB{limiter}"

    result = None
    if duck:
        # speech key: voice band (120 Hz - 4 kHz), stereo (sidechain wants the bed's layout). Measured
        # first, then gated just above the room tone and flattened, so every word pulls the bed down
        # by the same amount and the gaps let it go.
        band = f"aresample={SR},highpass=f=120,lowpass=f=4000,pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"
        kdb = frame_db(pcm(["-i", a.voice, "-vn", "-af", f"{band},atrim=end_sample={n},apad=whole_len={n}"], 2)[:n])
        floor = max(float(np.percentile(kdb, 2)), -70.0)
        loud = float(np.percentile(kdb, 90))
        gate = float(np.clip(min(floor + 8, np.median(kdb[kdb > loud - 20]) - 8), -50, -12))
        speech = kdb > max(loud - 20, gate)
        makeup = float(np.clip(10 ** ((-20 - (gate + 3)) / 20), 1, 64))     # flattened speech ~ -20 dBFS
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", a.voice, "-vn", "-af",
                            f"{band},agate=threshold={10 ** (gate / 20):.6f}:ratio=20:range=0.001:attack=2:release=40:knee=1,"
                            f"acompressor=threshold={10 ** ((gate + 2) / 20):.6f}:ratio=20:attack=2:release=40:knee=1:"
                            f"makeup={makeup:.3f},atrim=end_sample={n},apad=whole_len={n}", "-c:a", "pcm_f32le", str(key)],
                           capture_output=True, text=True)
        if r.returncode:
            fail("can't read voice audio: " + r.stderr.strip()[-300:])
        ref = frame_db(bed) + gain
        audible = ref > -70

        def render(thr_db, out_args=None, post=""):
            fc = (f"[0]{vol}[b];[b][1]sidechaincompress=threshold={10 ** (thr_db / 20):.6f}:ratio={RATIO}:"
                  f"attack={ATTACK}:release={RELEASE}:detection=rms:link=average{post}[o]")
            args = ["-i", str(bed_raw), "-i", str(key), "-filter_complex", fc, "-map", "[o]"]
            if out_args:
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *args, *out_args], check=True)
                return None
            return ref - frame_db(pcm(args, 2)[:n])           # gain reduction per frame, dB

        thr = float(np.clip(-20 - a.duck / (1 - 1 / RATIO), -60, 0))
        for it in range(6):
            gr = render(thr)
            got = float(np.median(gr[speech & audible])) if (speech & audible).any() else 0.0
            if abs(got - a.duck) < 0.3:
                break
            new = float(np.clip(thr + (got - a.duck) / (1 - 1 / RATIO), -60, 0))
            if new == thr:
                break
            thr = new
        result = (thr, gr, it + 1, floor, gate)
        post = f",afade=t=in:st=0:d={fi:.3f},afade=t=out:st={S - fo:.3f}:d={fo:.3f}"
        render(thr, ["-t", f"{S:.6f}", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2", a.out], post)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(bed_raw), "-af",
                        f"{vol},afade=t=in:st=0:d={fi:.3f},afade=t=out:st={S - fo:.3f}:d={fo:.3f}",
                        "-t", f"{S:.6f}", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2", a.out], check=True)

# ---- report ------------------------------------------------------------------------------------
oI, oTP = loudness(a.out)
odur, _ = probe_audio(a.out)
print(f"music: {track.name} ({tdur:.1f}s, from {start:.2f}s{f', looped {loops}x' if loops else ''}) -> {S:.2f}s bed")
print(f"  voice {vI:.1f} LUFS; bed gain {gain:+.1f} dB -> {target:.1f} LUFS in the gaps"
      f"{' (limited to -1.5 dBFS)' if limiter else ''}; fades {fi:.2f}s in / {fo:.2f}s out")
if result:
    thr, gr, passes, floor, gate = result
    sp, gp = speech & audible, ~speech & audible
    # frames >= 0.4 s after the last speech frame, and recovery time after each pause >= 0.6 s
    since = np.full(len(speech), 1e9); last = -1e9
    for i, s in enumerate(speech):
        last = i if s else last
        since[i] = (i - last) * HOP / SR
    late = gp & (since >= 0.4)
    rec = []
    i = 0
    while i < len(speech):
        if speech[i] and i + 1 < len(speech) and not speech[i + 1]:
            j = i + 1
            while j < len(speech) and not speech[j]:
                j += 1
            if (j - i - 1) * HOP / SR >= 0.6:
                k = next((m for m in range(i + 1, j) if gr[m] < 1.0), None)
                if k is not None:
                    rec.append((k - i) * HOP / SR)
            i = j
        else:
            i += 1
    med = lambda m: f"{np.median(gr[m]):.1f} dB" if m.any() else "n/a"
    print(f"  duck: voice floor {floor:.1f} dB, key gate {gate:.1f} dB; threshold {thr:.1f} dB ({passes} pass"
          f"{'es' if passes > 1 else ''}), ratio {RATIO:g}, attack {ATTACK} ms, release {RELEASE} ms; "
          f"speech {speech.mean() * 100:.0f}% of frames")
    print(f"  gain reduction: speech {med(sp)} (p10-p90 {np.percentile(gr[sp], 10):.1f}..{np.percentile(gr[sp], 90):.1f})"
          f" | all gaps {med(gp)} | gaps >=0.4s after speech {med(late)}"
          f" | recovery to <1 dB {np.median(rec):.2f}s median over {len(rec)} pauses" if sp.any() and rec else
          f"  gain reduction: speech {med(sp)} | gaps {med(gp)} (no pause >= 0.6 s to time the recovery)")
print(f"  bed alone: {oI:.1f} LUFS integrated, true peak {oTP:.1f} dBTP; under speech ~{a.level:+.0f} dB vs voice")
print(f"  wrote {a.out} ({odur or 0:.3f}s, AAC 48 kHz stereo)")
