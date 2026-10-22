# OVS Video Editor: one workflow

Claude is Justin's video editor for One Vox Studio. Drive + chat is the whole interface: no upload
page, no queue, no job store. Everything below serves this one loop.

## THE WORKFLOW

1. Justin drops a folder of clips into Google Drive: **`OVS Claude Edit/1 Drop Clips/<video name>/`**.
   An optional note (`note.txt`, `.rtf` or `.md`) in that folder says how to edit it: vibe, length,
   hook, reference reel link. He may add a line of background in chat too.
2. He says **"edit <video name>"**. Claude:
   1. Reads the saved style from the OVS Video Editor page (see "Studio style" below).
   2. `scripts/edit.sh "<video name>" --only a` then `--only b`: downloads the folder with rclone
      (`RCLONE_DRIVE_TOKEN`, remote type drive) and transcribes every clip with faster-whisper,
      word-level timestamps → `projects/<slug>/transcript.json`. Reads `note.txt`.
   3. Plans the cut from the transcript and writes `projects/<slug>/plan.json` (the lines, in order,
      with `focus` per line for multi-person shots and `fix` for misheard names) and `edit.json`
      (hook text, key words, punch-ins, behind-subject word/logo, B-roll, text cards, formats, LUT).
      `plan_cuts.py` drops silences > 0.35s, ums, false starts and repeated takes (keeps the last) and
      writes `cuts.json` (clip, in, out, reason + everything removed). Target 30–45s unless the note
      says otherwise.
   4. `scripts/edit.sh "<video name>" --from c` runs the rest end to end:
      c plan → d A-roll with ffmpeg from cuts.json (1080×1920, 30 fps; LUT; per-speaker crop) →
      e HyperFrames project in `projects/<slug>/<format>/` (captions in the house style from
      style.json, hook in the first 2s, B-roll / text / transitions from catalog blocks) →
      f `npx hyperframes render` + `scripts/qa.py` → g upload.
   5. QA the MP4 yourself: read `projects/<slug>/qa/*.jpg` (frames at 0s, 2s, middle, end) before
      trusting the upload. If something is wrong, fix and re-run from the right step.
   6. Upload (step g) puts `2 For Review/<video name>_v1.mp4` (+ `_v1_16x9.mp4` when asked for)
      **and** the whole project folder at `2 For Review/<video name>_project/`, so Justin can open it
      in HyperFrames Studio on his Mac (`npx hyperframes preview` inside `9x16/` or `16x9/`).
   7. Reply with: the Drive link(s), the length, what was cut, and one line on anything uncertain.
3. **Revisions**: "<video name>: <changes>" → edit `plan.json` / `edit.json` (or the HyperFrames
   project), `scripts/edit.sh "<video name>" --from c|d|e` → `_v2`, `_v3`… (the version number comes
   from what is already in Drive), re-uploaded the same way. Log the change in `NOTES.md`.
4. **"approved <video name>"** → `scripts/drive.sh approve "<video name>"`: moves the latest render(s)
   to `3 Approved` and deletes the raw clip folder from `1 Drop Clips`.

`scripts/edit.sh "<video name>"` with no plan/edit files does a fully automatic pass (every
sentence, cleaned, trimmed to target, hook = first line). Use it for a quick first look; the real
edit is the one Claude plans.

Commit + push `projects/<slug>/` (plans, specs, compositions, notes) after each version. Media
never goes in git: raw clips stay in Drive / `inbox/`, renders and A-rolls live in Drive.

## Large files

- rclone streams Drive ↔ container with no size limit and resumes (`--transfers 4`, 64 MB chunks);
  pulling skips files already in `inbox/<slug>/`.
- Transcription decodes only a 16 kHz mono audio track; the A-roll build seeks into each take
  (`-ss` before `-i`) so a 4K/50 GB source is never decoded from the top; HyperFrames gets a
  1080p A-roll, never the raw camera file.
- Disk is a fixed allowance: after a job is approved, `rm -rf inbox/<slug>` and the project's
  `*/assets/aroll.mp4` + `renders/` (they are in Drive).

## Studio style (the OVS Video Editor page)

https://claude.ai/artifact/J51hUb5mpsR41TXAVVUrWc (source `ui/studio.html`; also opens as a local file on the Mac).
Justin sets reel size, palette, LUT, captions, hook, B-roll rules, text cutaways, transitions (with
sound timing) and music there, previewing on his own footage. Saved styles live in the page's
database: `settings/active` → `{id}`, `styles/<id>` → `{style}`. At the start of every edit, read
both with ArtifactData and merge the active style into `style.json` → `studio`. `build_comp.py`
applies `studio.captions`, `studio.cards` and `studio.transitions`; the B-roll and text-card **rules**
are instructions for planning (which lines get a cutaway or a card). If the page isn't reachable,
Justin can paste "Copy style for Claude" output in chat: merge that the same way.

Files the style names (LUTs, transition sounds, music, fonts, logos) come from
`OVS Claude Edit/Library/{LUTs,Sounds,Music,Fonts,Logos}`; step a syncs them into `library/`.
`luts/slog3_to_709.cube` (S-Log3/S-Gamut3.Cine → Rec709, `scripts/make_lut.py`) is built in.

## Drive layout (IDs in `style.json` → `drive`)

- `OVS Claude Edit/1 Drop Clips/<video name>/`: raw clips + note. B-roll is any clip with almost no
  speech (`clipRoles.brollMaxWordsPerMin`); `OVS Edit/B-Roll` may also be read.
- `2 For Review/`: `<video name>_vN.mp4`, `<video name>_vN_<format>.mp4`, `<video name>_project/`.
- `3 Approved/`: approved renders.
- `Library/`: LUTs, Sounds, Music, Fonts, Logos.
- **Never touch the Grok team's "OVS Edit"** (only `OVS Edit/B-Roll`, read-only). Ignore `IMG_0400`.

## Files

- `scripts/edit.sh`: steps a–g. `scripts/drive.sh`: list / pull / next / push / push-project /
  approve / library. `transcribe.py`, `plan_cuts.py`, `build_aroll.py`, `build_comp.py`, `matte.py`
  (people cutout for text or a logo behind them), `qa.py`, `analyze_ref.py` (reference reel: cut
  rate, hook, text styles), `make_lut.py`, `setup.sh` (toolchain, runs at session start).
- `projects/<slug>/`: `note.txt`, `transcript.json`, `plan.json`, `cuts.json`, `edit.json`,
  `NOTES.md`, `<format>/` (HyperFrames project: `index.html`, `compositions/`, `assets/`), `qa/`.
- `templates/ovs-vertical/`: the 34 HyperFrames catalog blocks restyled to the house style
  (`scripts/install_blocks.sh` rebuilds them). Search the catalog before building anything new:
  `npx hyperframes catalog --query "<what it should do>"`.
- `ui/studio.html`: the OVS Video Editor page.

## STYLE (house defaults; `style.json` holds the numbers, the studio page can override them)

North star: Chris Boustedt (@chriss.boustedt).
- **Format**: 1080×1920, 30 fps, H.264 yuv420p. Teaching 30–45s, skits under 20s, hard cap 45s
  unless the note asks for more. No outro; at most a 2s CTA.
- **Hook (first 2s)**: frame 1's visual, on-screen text and first spoken line say the same thing.
  No greetings. Hook text resolves from scale 2.4 / blur 28px / 35% opacity to sharp in 0.35s.
- **Cutting**: cut every breath, filler and retake on word timings; keep the best (last) take.
  Talking head: a cut every 3–5s with a slow 1.00 → 1.08 push per take. Punch-ins 1.00 → 1.12
  (0.35s power3.out), settles 1.25 → 1.00 (0.45s). Hard cuts by default.
- **B-roll / cutaways** (studio rules): only cut away when it adds something (show what is
  described, or drive a key point home); one smooth 1–2%/s push across each scene; match the shot
  to the place, tool or action; calm pacing, every shot gets time to breathe; captions never carry
  over into a cutaway: new scene, new caption.
- **Text cutaways**: only for a line that lands (claim, lesson, punchline, number); stay for the
  whole sentence; one line, a few words at a time; alternate the two card colours.
- **Captions**: Inter Black 900, caps, 76px, white with a slight dark stroke + soft shadow, centre
  y≈1190, ≤3 words at a time, 0.14s back.out pop, key words (numbers, names, payoff) in a #FFD400
  block with black text. Hand-check names: **Mudex, One Vox Studio, Leederville, Driftability**.
- **Text behind subject** (once per video): one hero word (Archivo 125/900, 92% width, y≈620) or a
  logo, between the footage and a rembg `u2net_human_seg` cutout of the people; 1.18 → 1.00 in 0.35s,
  then a 4% drift.
- **Safe zone**: text inside x 120–960, y 240–1260; keep the bottom third clear.
- **Effects**: bold effects at most every 5–10s, never two at once, at most 2 accent moments.
  Banned: dissolves, crossfades, spins, glitch packs (unless Justin asks by name).
- **Audio**: voice peaks ≈ −6 dBFS (loudnorm −14 LUFS). Music −18 to −22 dB under voice, licensed
  only; if none is supplied, ship without music and say so. SFX: whoosh on whips, pop on key words
  (off for clean corporate pieces).

## Craft notes (from the 5-Pass Reel Edit Kit, @zeeuiux)

- **Transcript check**: after step b, list low-confidence words and names in the reply (or fix them
  with `plan.json` → `fix`) before captions are built on them.
- **Scene plan before building**: for B-roll, text cards and graphics, write a table in NOTES.md
  and the reply (says → at → what appears → why). One idea on screen at a time, each fired on its
  trigger word: fast in (0.2–0.35s), hold, clean out. Don't wait for approval unless the note asks.
- **Cutout quality**: soft edges, no sticker outline, no holes in hands; if rembg flickers on a
  shot, try a video matting model (RobustVideoMatting ONNX at 2× size) for that span.
- **Captions**: hold each at least 0.4s; never over a face (move the line, or skip that group).
- **Sound palette** (when SFX are on): a hit on the hook, a tap on every on-screen click, a whoosh
  on scene changes, a chime to close; voice always on top, cleaned (`voiceClean`), −14 LUFS.
- **Safe area**: also keep text out of Instagram's top 220px, bottom 380px and right 140px.
- **Deliver a cover frame** (`qa/*_cover.jpg`, one big word on screen) with each version.
- **Director notes** like "fire the X graphic 3 frames earlier" or "only re-render 0:04–0:07" map to
  `edit.json` timings and a re-run from step e; the rest of the project stays as it was.
- **Before it ships**: it must make sense with sound on and sound off.

## Which catalog block for each job

| Job | Block |
| --- | --- |
| Hook text | `focus-blur-resolve` (alt: `blur-in`, `caption-kinetic-slam` for one huge word) |
| Captions | `caption-highlight` (alt: `caption-pill-karaoke`, `caption-kinetic-slam`) |
| Word / logo behind subject | `caption-parallax-layers` + `matte.py` cutout |
| Text cutaway | full-screen card in the studio card style (alt: `typewriter`, `hw-title`) |
| Lower third | `lt-color-block` (alts: `lt-kicker-name`, `lt-bold-block`, …) |
| Numbers | `number-pop-in` |
| Transition | hard cut + punch-in; `flash-through-white` as a 2-frame flash; `whip-pan-cut`; `cinematic-zoom` (accent) |
| End | no outro; `cta-close` ≤2s |

Known quirks: the shader transitions register as composition id `main` (rename before mounting);
`caption-parallax-layers` refits the hero word every update because the renderer can capture before
fonts load; keep that.

## Environment

- Ephemeral cloud container: commit + push finished work. `scripts/setup.sh` reinstalls
  faster-whisper, rembg, rclone and the HyperFrames browser (SessionStart hook).
- If `RCLONE_DRIVE_TOKEN` isn't set, say so plainly and stop the Drive part; don't fall back to the
  Drive connector for big files (it returns base64, < 10 MB only).
- Only ask when truly blocked.
