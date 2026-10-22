# Editor — autonomous HyperFrames video editing for One Vox Studio

Claude acts as Justin's autonomous video editor. Skills live in `.claude/skills/`
(hyperframes, hyperframes-cli, hyperframes-registry, media-use, …) — load the relevant ones
before building. Every composition reads `style.json`; the STYLE section below is the
human-readable version of it. If they disagree, update both.

## Inputs

### Primary: Google Drive "OVS Claude Edit" (rclone, no size limit)
Claude's own inbox, separate from the Grok team's "OVS Edit". IDs are pinned in `style.json` →
`drive`. All Drive transfers go through `scripts/drive.sh` (rclone + `RCLONE_DRIVE_TOKEN` from the
environment; it loads at session start, and `scripts/setup.sh` installs rclone).
- `1 Drop Clips/<Video Name>/` — one subfolder per video:
  - **A-roll**: the clips where someone talks to camera.
  - **B-roll**: any footage without meaningful speech (fewer than `clipRoles.brollMaxWordsPerMin`
    words/min after transcription). Also usable: `OVS Edit/B-Roll`, **read-only**.
  - **Reference** (optional): a video with `ref` in its file name and/or `note.txt` with a reel link
    and notes. See "References" below.
- `2 For Review/` — renders, named exactly after the subfolder: `<Video Name>_v1.mp4`, `_v2`… plus
  `<Video Name>_v1_hook-B.mp4` … `_hook-E.mp4`.
- `3 Approved/` — Justin moves the approved render here. **After that, delete that video's raw
  subfolder from 1 Drop Clips** (`drive.sh cleanup`; run `--dry-run` first and log what it removes).
- **Don't touch the Grok team's "OVS Edit"**: not its `1 Drop Clips` or `2 For Review`, and
  `IMG_0400` is their job, so ignore it. Only `OVS Edit/B-Roll` may be read.
- Fallbacks: the Drive connector only for files under 10 MB (it returns base64); the inbox page
  for small uploads.

### "Process the inbox"
1. `scripts/drive.sh cleanup` (approved → delete raw subfolder), then `scripts/drive.sh scan`:
   every subfolder of 1 Drop Clips with no `<Video Name>_v*.mp4` in 2 For Review or 3 Approved is
   a job. Also take queued jobs and revisions from the inbox page (below).
2. If `RCLONE_DRIVE_TOKEN` isn't visible, say so plainly and stop the Drive part. Don't fall back
   to the connector for big clips.

### Inbox page (Cutting Room Inbox)
https://claude.ai/artifact/G5w5iJcPT376URSdZ11hmZ (source `ui/edit-inbox.html`).
- Job types: `drive-inbox` (a subfolder of OVS Claude Edit/1 Drop Clips, or `drive.scanAll` = every
  new folder), `drive` (a pasted folder link), `upload` (small files only, in pieces, see below).
- Queuing calls `comments.sendToClaude`, which wakes a Claude session watching the artifact. With no
  session the page shows "Tell Claude: process the inbox" + Copy. Claude can't poll on its own.
- Collections: `jobs/<id>` and `revisions/<id>` ({jobId, v, feedback, status}).
- Live status: build a patch with `scripts/job_status.py <doc.json> <status> <pct> "<step>"` and
  send it with ArtifactData `update` (pin `if_version`). Statuses: queued → downloading → cutting →
  captions → rendering → qa → done (or needs-input with `question`, or failed).
- When done, set `versions: [{v, feedback, result: {preview, hooks[{label,line,asset}], qa[{label,
  pass,note}], summary, outputPath, driveUrl, length, size}}]`, `version`, `status: done`.
  Previews are uploaded as assets (≤15 MB each via the Artifact tool: re-encode, see
  `projects/artemis-soundbites/NOTES.md`). Revisions: mark the revision doc `done` and append the
  next version.
- Upload pieces: each = one 0x00 byte + ≤14 MB of the file, stored as video/mp4. Fetch each piece
  with Artifact `read` and a single `path` (bulk `paths` does not reach assets), rebuild with
  `scripts/join_pieces.py`, check the size/sha256. **Auto-free**: once the original is in the repo
  (Git LFS, confirm with `git lfs push --object-id origin <oid>` returning 0 B) or in Drive, delete
  the job's pieces (Artifact `delete`, one per id) and set `storageFreed: true`.

### References
`scripts/analyze_ref.py <ref.mp4> <dir>` measures cut rate (hard cuts and jump cuts), shot
lengths, the hook line and when speech starts, pace and loudness, and writes `hook.jpg` (first 3s at
8 fps) and `reel.jpg` (1 fps). Read both sheets for text styles and placement, caption style,
transitions and zooms. For a reel link in note.txt, download it if the link allows (otherwise work
from the notes and say so). Write what differs from house style as overrides in the edit spec and
in NOTES.md ("Reference match"), choosing the closest catalog blocks (see CATALOG BLOCKS). Anything
the reference doesn't show stays house style.

## Layout
- `inbox/<job-slug>/` — media pulled for a job in progress (git-ignored).
- `projects/<job-slug>/` — the editable project: `plan.json` (chosen lines), `cuts.json`,
  `edit.json` (spec), `index.html` + `compositions/`, `assets/`, transcript, tracking, `NOTES.md`.
- `done/<job-slug>/` — originals (Git LFS) + sha256; renders live in `projects/<job-slug>/renders/`.

## Job workflow
1. Pull the subfolder (`drive.sh pull`), sort clips into A-roll / B-roll / reference, read note.txt.
2. Transcribe A-roll (`scripts/transcribe.py`), track the speaker (`scripts/subject_track.py`),
   analyse any reference (`scripts/analyze_ref.py`).
3. Pick the lines → `plan.json`; `scripts/cutlist.py` makes word-accurate takes (pauses > 0.28s and
   fillers cut). `scripts/build_aroll.py` reframes 9:16 and levels the voice (peaks −6 dBFS).
4. Write `edit.json` (hook text, chapters, punch-ins/settles, key words, B-roll, lower third, hero
   word + `scripts/matte.py` cutout, reference overrides); `scripts/build_comp.py` generates the
   HyperFrames project from the restyled catalog blocks. Lint, snapshot, look.
5. `scripts/qa_check.py` (DELIVERY CHECKLIST) must pass before rendering for delivery.
6. Render `<Video Name>_v1.mp4`, then `scripts/build_hooks.sh` for the 4 alternate hooks (hooks.json).
7. `drive.sh push` all five to 2 For Review; commit originals (LFS) + project + renders; push.
8. QA note in NOTES.md; report the Drive link(s).

No music until licensed tracks exist: ship without it and say so. Only ask when truly blocked.

## Feedback iterations
"Tighter", "change caption style"… → edit `plan.json` / `edit.json`, rebuild, re-render as the next
version (`_v2`, `_v3`), push to 2 For Review, log the change in NOTES.md, update the job card.

## STYLE
North star: Chris Boustedt (@chriss.boustedt). Values below are mirrored in `style.json`.

### Format and length
- 1080×1920, 30 fps, H.264 (yuv420p) MP4.
- Skits under 20s. Teaching 15–45s. Hard cap 45s. Never 50–70s.
- End fast: no outro. At most a 2s handle or CTA card.

### Hook (first 3s)
- On frame 1 the visual, the on-screen text and the first spoken line all say the same thing.
- No greetings, no intros. Start on the strongest line.
- Hook text: first words start at scale 2.4, blur 28px, 35% opacity → scale 1, sharp, 100%
  over 0.35s. Blurred and glow font reveals are liked.

### Cutting and pacing
- Jump-cut every breath, filler word and retake. Cut on word timings and keep the best take.
- Talking head: a jump cut every 3–5s, slow zoom 1.00 → 1.08 (linear) across each take.
- B-roll every 1.5–2s. Montages every 0.5–0.7s. Something new on screen at least every 2s.
- Hard cuts only. Punch-ins 1.00 → 1.12 over 0.35s (power3.out). Scale-out settles
  1.25 → 1.00 over 0.45s (power3.out).
- Banned: dissolves, crossfades, spins, glitch packs.

### Captions (default on)
- Inter Black 900, ALL CAPS, 76px, white, slight dark stroke + soft shadow, no box.
- Centred horizontally, centre at y≈1190.
- One word or a short phrase (≤3 words) at a time, popping in over 0.14s (back.out).
- Key words (numbers, names, payoff) sit in a solid #FFD400 block, black text, 10px radius.
- Hand-check these names in every transcript: **Mudex, One Vox Studio, Leederville**.

### Chapter pills
- #FFD400 pill, top-left at x120 y250, black Inter Black 28px caps. Changes each section.

### Text behind subject (once per video)
- On the hero word only. One caps word in the heading face, auto-fit to ~92% of frame width,
  centred around y≈620 so the head and hands cross it.
- Layers: footage → giant word → footage again masked to the subject with a per-frame rembg
  matte (`u2net_human_seg`).
- In: scale 1.18 → 1.00 over 0.35s, then a slow 4% drift.

### Headings
- Goal: Druk Wide (not licensed yet). Fallback: Archivo, width 125, weight 900.
- The font is a variable (`style.json` → `fonts.heading`); swap it there once licensed.

### Safe zone
- All text inside x 120–960, y 240–1260. Keep the bottom third clear for platform UI.

### Graphics and effects
- B-roll matches the spoken words. One pop-up graphic per mention, held ≤2s.
- Bold effects at most once every 5–10s, never two at once. At most 2 accent moments per video.

### Audio
- Voice peaks around −6 dBFS. Music −18 to −22 dB under the voice. No lyrics under speech.
- SFX: whoosh on whips, pop on keywords.
- Commercially licensed music only. If none is supplied, ship without music and say so.
  Never pull random tracks.

## CATALOG BLOCKS
Prefer HyperFrames catalog blocks over building from scratch. Before hand-building anything
new, search the catalog first (`npx hyperframes catalog --query "<what it should do>"`); if
something new is adopted, add it to `templates/ovs-vertical/blocks.txt` and give it a restyle
rule in `scripts/restyle_blocks.py`.

- **Template:** `templates/ovs-vertical/` (1080×1920) holds all 34 blocks, already restyled to
  the house style: Inter Black, #FFD400 accent with black text on it, Archivo width 125 for
  headings, text inside the safe zone. The restyle is a script, so it can be rebuilt from the
  catalog at any time with `scripts/install_blocks.sh` (reinstall + `scripts/restyle_blocks.py`
  + lint).
- **Mounting:** a block mounts with `data-composition-src="compositions/<name>.html"`. A
  component in `compositions/components/` has its markup/style/script merged into the scene;
  some (e.g. `focus-blur-resolve`) only give their timeline recipe in a comment block.
- **Captions:** words come from `scripts/transcribe.py`. Replace the block's `WORDS` array and
  its groups (≤3 words). Mark key words (numbers, names, payoff) with `key: true`.

### Which block for each job
| Job | Default block | Alternates / notes |
| --- | --- | --- |
| Hook text (first 3s) | `focus-blur-resolve` (2.4× → 1×, blur 28px → 0, 35% → 100% opacity over 0.35s, phrase scales as one unit) | `blur-in`. For a single huge word: `caption-kinetic-slam` |
| Captions (default) | `caption-highlight` (white Inter Black 76px caps at y≈1190, 0.14s back.out pop, `key: true` words in a #FFD400 block) | "Karaoke" style → `caption-pill-karaoke`. "Word-pop" style → `caption-kinetic-slam` (one word at a time, big) |
| Text behind subject (once per video) | `caption-parallax-layers` (hero word in Archivo 125/900, fitted to 92% width around y≈620, 1.18 → 1 over 0.35s then 4% drift). Put the rembg subject cutout (`scripts/matte.py`) on a layer above it | `mk-emphasis-type` for a low-contrast background word texture |
| Chapter pill | `spring-pop` holding the pill (top-left x120 y250) | |
| Lower third (name/role) | `lt-color-block` (yellow block, black Inter Black caps) | `lt-kicker-name`, `lt-bold-block`, `lt-stack-bars`; quieter: `lt-accent-underline`, `lt-side-rule`, `lt-clean-bar`, `lt-dark-card`, `lt-soft-pill`, `lt-mask-reveal`, `lt-neon-border` |
| Numbers / stat pop-ups | `number-pop-in` | `spring-pop` for a badge |
| Keyword hit (with the "pop" SFX) | `beat-accent` | |
| Typed text on screen | `typewriter` | `typed-prompt` (AI prompt), `notes-typing` (notes app) |
| Handwritten annotation | `hw-title` (word-by-word highlight) | `hw-write-title` (true write-on). Caveat stays: handwriting is the point |
| Transition (default) | Hard cut, with punch-in 1.00 → 1.12 (0.35s power3.out) or scale-out settle 1.25 → 1.00 (0.45s). `cut-the-curve` for a velocity-matched hard cut | `whip-pan-cut` for whips (add the whoosh) |
| Accent transition (counts toward the max of 2 accent moments) | `cinematic-zoom` (zoom blur) | `flash-through-white` only as a fast flash, never as a slow dissolve |
| Banned by STYLE | `glitch`, `chromatic-radial-split` | Installed and restyled, but only used if Justin asks for them by name |
| End | No outro. `cta-close` as a ≤2s CTA card | `logo-outro` only when asked, trimmed to ≤2s |

Known quirks:
- The 4 shader transitions (`cinematic-zoom`, `flash-through-white`, `glitch`,
  `chromatic-radial-split`) register under the composition id `main`, which clashes with a
  project's root id. Rename the id inside the block before mounting one.
- `caption-parallax-layers` refits the hero word on every timeline update, because the
  renderer can capture before the heading font has loaded. Don't remove that.

## DELIVERY CHECKLIST (every render, before it ships)
- [ ] Hook lands on frame 1 (visual = on-screen text = first spoken line).
- [ ] Length within target for the type, never over 45s.
- [ ] Something changes on screen at least every 2s (check the cut list).
- [ ] Captions word-checked (incl. the names list) and inside the safe zone.
- [ ] No more than 2 accent moments.
- [ ] No watermarks.
- [ ] 4 alternate-hook versions exported (`_hook-A`…`_hook-D`); only the first 1–3s differ.

## QA note (append to `NOTES.md` after each job)
Date, version, final length, hook line (+ the 4 alternates), checklist results (pass/fail
per line), anything that needed judgement, Drive link(s).

## Environment notes
- Cloud container is ephemeral: always commit + push finished work. `scripts/setup.sh`
  reinstalls the toolchain (runs from the SessionStart hook in `.claude/settings.json`).
- MP4/MOV/media are tracked with Git LFS (`.gitattributes`).
- Drive token: `RCLONE_DRIVE_TOKEN` (environment setting, loads at session start).
- Toolchain: HyperFrames CLI + headless Chrome, ffmpeg, faster-whisper (word timestamps),
  rembg with `u2net_human_seg` (subject mattes).
