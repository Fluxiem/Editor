# Editor — autonomous HyperFrames video editing for One Vox Studio

Claude acts as Justin's autonomous video editor. Skills live in `.claude/skills/`
(hyperframes, hyperframes-cli, hyperframes-registry, media-use, …) — load the relevant ones
before building. Every composition reads `style.json`; the STYLE section below is the
human-readable version of it. If they disagree, update both.

## Inputs

### Primary: Google Drive (`OVS Edit/`)
Folder IDs are pinned in `style.json` → `drive` (another Drive also has a "B-Roll" folder:
never use it).
- `OVS Edit/1 Drop Clips/<Video Name>/` — one subfolder per video, named after the video:
  the clips plus an optional `note.txt` (the brief). Loose files at the root of
  `1 Drop Clips` = one job named after the first clip; ask only if that's ambiguous.
- `OVS Edit/B-Roll/` — reusable B-roll library. Read only. **Never delete, move or rename
  anything in it.**
- `OVS Edit/2 For Review/` — finished MP4s (main cut + 4 alternate hooks) go here.
- Transfer: the Drive connector's `download_file_content` caps at **10 MB** (base64; the result
  lands in a tool-results file, decode with `jq -r .content <file> | base64 -d > out`). Use it
  for `note.txt`, images and small clips only. Clips over 10 MB need the Drive API directly:
  `scripts/drive.sh` (rclone) once an `RCLONE_DRIVE_TOKEN` environment variable is configured.
  Without it, large clips can't be pulled. Say so instead of guessing at the footage.

### Secondary: Cutting Room Inbox (small files only)
Artifact: https://claude.ai/artifact/G5w5iJcPT376URSdZ11hmZ (source: `ui/edit-inbox.html`).
- Jobs live in its db collection `jobs` (fields: name, format, captions, length, brief, keep,
  links[], files[{name,size,type,pieceSize,chunks[]}], status, note, output, outputPath, createdAt).
- Every file is uploaded as ordered pieces (asset ids in `chunks`): each piece = one 0x00
  header byte + up to 19 MiB of the original. Storage is 1 GB per artifact in total.
- To process: `ArtifactData list jobs`, take `status == "queued"`, download every piece with
  `Artifact read paths=[...ids]`, rebuild with
  `scripts/join_pieces.py inbox/<job-slug>/<name> <piece files in chunks order>`, verify size.
- Status flow `queued` → `editing` → `rendered` (or `needs-input` with a question in `note`).
  Put the summary in `note`, the repo path in `outputPath`, and the MP4 asset id (≤15 MB) in
  `output`. Rendered jobs show a "Free storage" button for the user; don't delete pieces
  yourself unless asked.

## Layout
- `inbox/<job-slug>/` — media pulled down for a job in progress.
- `projects/<job-slug>/` — the editable HyperFrames project (compositions, assets,
  transcripts, mattes, `NOTES.md` with decisions, edit log and QA notes).
- `done/<job-slug>/` — sources once finished, plus `<job-slug>.mp4` and
  `<job-slug>_hook-A..D.mp4`.

## Job workflow ("process the inbox")
1. List `1 Drop Clips` (and queued artifact jobs). One subfolder = one job.
2. Pull clips + `note.txt` into `inbox/<job-slug>/`. ffprobe everything, snapshot keyframes,
   transcribe with faster-whisper (word timestamps), hand-check the names list.
3. Decide video type (skit / teaching), hook, structure, chapters, hero word, B-roll plan
   (pull matching clips from `B-Roll`). Write the plan to `NOTES.md`.
4. Copy `templates/ovs-vertical/` to `projects/<job-slug>/` and build from its restyled catalog
   blocks (see CATALOG BLOCKS) and `style.json`. Prefer a catalog block over hand-building.
5. Run the DELIVERY CHECKLIST. Fix anything that fails before rendering.
6. Render the main cut + 4 alternate hooks.
7. Upload the renders to `2 For Review`, move sources to `done/<job-slug>/`, commit + push.
8. Write the QA note in `NOTES.md` and report the Drive link(s) plus a short summary.

Only ask when truly blocked (missing critical asset, unclear must-keep moment).

## Feedback iterations
"Tighter", "change caption style", etc. → edit `projects/<job-slug>/`, re-render, re-upload
to `2 For Review` as a new version (`_v2`, `_v3`…), log the change in `NOTES.md`.
No Studio needed.

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
- Toolchain: HyperFrames CLI + headless Chrome, ffmpeg, faster-whisper (word timestamps),
  rembg with `u2net_human_seg` (subject mattes).
