# Editor — autonomous HyperFrames video editing for One Vox Studio

Claude Code is Justin's video editor. **The whole interface is Drive folders plus the chat command
`edit <folder name>`.** Don't add a second editor, a new repo, an upload page, a queue or a job
store. Rendering needs Claude Code; a plain Claude.ai chat or Project without Claude Code can't
render.

Skills live in `.claude/skills/` (hyperframes, hyperframes-cli, hyperframes-registry, media-use, …).
Load the relevant ones before building. Every composition reads `style.json`, and HOUSE LOOK below is
the human-readable version of it. If they disagree, update both.

## EDIT WORKFLOW (canonical: this replaces every earlier inbox/job workflow)

### Drive folders
IDs were verified with rclone on 2026-11-06 and are pinned in `style.json` → `drive`. Check before
using any other folder, and don't invent names or IDs.

| Folder | ID | Use |
| --- | --- | --- |
| `OVS Claude Edit/` | `13UItvrTqDvxww3rJhD5plq2lgJEOw1Hu` | Claude's own inbox, used for every Claude Code job |
| `  1 Drop Clips/` | `1_TAxCJa9V4eMYVretfStwxBfbI1mVwOQ` | one subfolder per video (Justin drops) |
| `  2 For Review/` | `10OBWAfflhNE8NmNv3EphOf7ie70gpfBE` | `<folder>_vN.mp4` + `<folder>_project/` |
| `  3 Approved/` | `1JT7bnmH6J2lSA7U8ZONTRs4k6E2c0GYC` | approved renders |
| `  Library/` | `1EEH-aUoZXcMCBInFhcg6aisUyChek-gm` | Fonts, LUTs, Logos, Music, Sounds (hit, tap, chime), Transitions |
| `OVS Edit/` (Grok team) | `1JovciMDuW9QzS9fdwLzjGPlc2RNQF4i4` | **Don't touch** its 1 Drop Clips, 2 For Review or 3 Approved, and never take their jobs |
| `  B-Roll/` | `128fTy29nYqmCcs12azNBrzJSuRm3dfL6` | shared, read-only |
| `  References/` | `1_HFWC73_xQy30vpRXJsFg9DOFngd9h41` | shared, read-only |

All Drive transfers go through `scripts/drive.sh` (rclone + `RCLONE_DRIVE_TOKEN`):
`pull <folder> <dir>` · `push <file.mp4>` · `push-project <dir> <folder>` · `review` ·
`approve <file.mp4> [--dry-run]` · `broll|refs|library [<file> <dir>]` · `scan`. `scan` only
*lists* Drop Clips folders that have no render yet. It never starts a job.

### Trigger
Justin drops one folder per video into `OVS Claude Edit/1 Drop Clips/<folder name>/`:
- his footage (required);
- optional B-roll or backgrounds for this job;
- optional reference: a video with `ref` in its file name, **or** `note.txt` with a reel link
  ("copy this: …") plus edit notes (vibe, length, hook).

Then he types **`edit <folder name>`**, which may carry inline notes:
`edit Driftability, keep it under 30s`. The inline notes and note.txt are this job's brief and
override house defaults for this job only. Jobs start only on that command. If the folder is
cancelled or stopped (see Hard stops), don't start it: say so and ask.

### What `edit <folder name>` does
Paths: `inbox/<folder>/` holds the media (git-ignored) and `projects/<folder>/` holds the project.
Use the folder name as-is; only replace characters that break paths (`:` `/` `\`) with `-`.

**a) Download.** `scripts/drive.sh pull "<folder name>" inbox/<folder>/`. Big clips need
`RCLONE_DRIVE_TOKEN`. Without it, fetch files under ~10 MB through the Drive connector and stop on
anything bigger: say plainly that the token is missing. Never skip footage silently. Sort the clips:
A-roll is speech; B-roll has fewer than `clipRoles.brollMaxWordsPerMin` words/min; reference is the
`ref` file or note.txt. Read note.txt.

**b) Transcribe** every clip with faster-whisper at word level:
`scripts/transcribe.py <clip> projects/<folder>/transcripts/<clip>.json`. Several A-roll clips are
joined in recorded order (ffmpeg concat) into one source. Their word lists, offset by each clip's
start in that source, become `projects/<folder>/transcript.json`. Hand-check **Mudex, One Vox
Studio, Leederville**. Track the speaker with `scripts/subject_track.py`. Analyse any reference with
`scripts/analyze_ref.py` (see References).

**c) Plan the cut** from the transcript into `plan.json`, then run `scripts/cutlist.py` to get
`cuts.json`.
- Drop long silences, ums, false starts and repeated takes. Keep the best take, or the last complete
  one.
- Keep natural pauses so the speaker finishes sentences. **No jittery over-cutting.** The defaults
  keep pauses ≤ 0.7s with a 0.2s tail (style.json `cuts`). "Like", "you know" and "basically" are
  cut only where they're clearly filler.
- Preserve the intended meaning and complete sentences. Never retime or slow the voice.
- Aim for 30–45s unless the notes say otherwise. If the essential content can't fit, propose the cut
  or a split in the storyboard. Never drop essential content silently.

**d) STORYBOARD FIRST, before any full render.**
- If neither the notes nor note.txt name a vibe (BOLD or CLEAN, see HOUSE LOOK), ask once, together
  with the proposed cut.
- Write `edit.json`, build the project (step f), and snapshot **one still per moment** (hook, each
  beat, each B-roll/graphic/photo, text-behind-subject, end) with the text and graphics already
  placed: `npx -y hyperframes@0.8.185 snapshot`. Save the stills in `projects/<folder>/storyboard/`
  with a list giving each still's timecode, spoken line and what's on screen. Show them to Justin
  (SendUserFile) together with the length and what was cut.
- For every **full-screen motion graphic**, fill in this brief and show a **preview still** first:
  "When the video says [exact line], show [what] full-screen, in brand colours/font, max 3 icons,
  one big headline, no small text, 2–3s, then cut back to the speaker."
- **Stop and wait for Justin's notes on the stills.** Apply them, and only then render.

**e) Assemble the A-roll** with ffmpeg: `scripts/build_aroll.py` gives 1080×1920 at 30 fps, reframed
on the speaker, with voice peaks around −6 dBFS, at **natural voice speed (no atempo)**.

**f) Build the HyperFrames project** in `projects/<folder>/` on that A-roll: `edit.json` →
`scripts/build_comp.py` → `index.html` + `compositions/` + `assets/`, all kept editable. Match any
reference's pacing, text style and transitions with the closest catalog blocks. Use only HyperFrames
Free and the house template (CATALOG BLOCKS). Never call Pro-only skills. Then run
`npx -y hyperframes@0.8.185 check`, look at the snapshots, and run `scripts/qa_check.py` (DELIVERY
CHECKLIST). It must pass. Pass `--max-sec` / `--min-sec` when the notes set another length.

**g) Render and deliver both:**
1. The finished MP4 (`npx -y hyperframes@0.8.185 render`) → `scripts/drive.sh push` →
   `OVS Claude Edit/2 For Review/<folder name>_vN.mp4`.
2. The editable project folder → `scripts/drive.sh push-project projects/<folder> "<folder name>"`
   → `2 For Review/<folder name>_project/`, so Justin can open it in HyperFrames Studio. It must
   include `index.html`, `compositions/`, `assets/` (with `aroll.mp4`, which is git-ignored but
   needed), `hyperframes.json`, `package.json` and `meta.json`.

Commit the project and renders (renders go through Git LFS) and push the branch.

**h) Reply** with the Drive links, the length, what was cut, and one line on anything you're unsure
of. Append the QA note to `projects/<folder>/NOTES.md`.

### Revisions
Justin watches the **whole** cut, then sends **all** his notes in one batch. Apply the whole batch
once to `plan.json` / `edit.json`, rebuild, and re-render as the next version (`_v2`, `_v3`…).
Push it, refresh `<folder>_project/`, log the change in NOTES.md, and reply as in (h).

### Approved
When Justin approves a version, run `scripts/drive.sh approve "<folder name>_vN.mp4"` (dry-run first),
which moves that render to 3 Approved. **Keep the raw clip folder in 1 Drop Clips.** Delete raw clips
only when Justin explicitly says so, and then only the folder he named.

### Saving preferences
A lasting preference is edited into HOUSE LOOK (and `style.json`) in place: replace the rule it
supersedes, and don't leave duplicates. Job-specific notes and revision notes stay with that job in
`projects/<folder>/NOTES.md`. Don't turn a one-off request into a standing rule.

### Hard stops
- **Never restart cancelled jobs.** IMG_0400 and DJ Headshots were CANCELLED on 2026-11-05.
  Driftability / "Mudex: Driftability" is STOPPED. They're listed in `style.json` →
  `drive.ignoreJobs` (`drive.sh pull` refuses them). Restart one only if Justin explicitly asks to
  restart it.
- Never delete raw clips by default.
- Never post or upload anything publicly. `hyperframes publish`, `cloud`, `lambda` and `cloudrun`
  are off-limits.
- Never buy, upgrade or authenticate paid HyperFrames features. HyperFrames is pinned to
  **0.8.185 (Free)** in this repo; the Grok box runs 0.8.214, also Free 0.8.x. Always run
  `npx -y hyperframes@0.8.185 …`, because bare `npx hyperframes` fetches the latest 0.9.x. Don't run
  `hyperframes upgrade` or `hyperframes skills`: the seven installed skills are stale, but leave them
  as they are.
- Pro only (not installed, needs ~v0.9.9+): `reverse-any-video` and `/style-sampling`. Treat
  style-sampling as knowledge only. Its five Pro explainer styles (Collage, Finance, Animated Science,
  3D Brand, 3D True Crime) are **not adopted**, so don't promise or pull them. No Pro skills, paid
  template pulls or CLI upgrade unless Justin approves a separate trial away from production jobs.
- Don't touch the Grok team's live jobs in `OVS Edit/1 Drop Clips`.

### Available now vs blockers (checked in this Claude Code environment on 2026-11-06)
| Component | Status |
| --- | --- |
| Claude Code on Fluxiem/Editor + `edit <folder name>` | ready (this file) |
| `RCLONE_DRIVE_TOKEN` + rclone | present; every folder above listed OK. ⚠ rclone warns that it uses rclone's shared Google Drive client_id, "being retired … during 2026". If transfers start failing, make an own client_id and re-authorize, then update the env setting |
| faster-whisper (small.en), ffmpeg 6.1, rembg u2net_human_seg | ready |
| HyperFrames 0.8.185 Free + Chrome headless | `doctor` OK for rendering; the house template lints clean (whisper-cpp/Docker missing, not needed) |
| Licensed music | none: `Library/Music` is empty, so ship without music and say so |
| Druk Wide | not available (`Library/Fonts` is empty); use the Archivo fallback |
| OVS style-guide v4.9 §W | not in this repo; the storyboard-first rule above is the version in force |
| Pro skills / template pull / v0.9.9+ | unavailable by design; don't call them |

If the token is missing in a future session, stop the Drive part and say so plainly.

### References
`scripts/analyze_ref.py <ref.mp4> <dir>` measures the cut rate (hard cuts and jump cuts), shot
lengths, the hook line and when speech starts, pace and loudness. It writes `hook.jpg` (first 3s at
8 fps) and `reel.jpg` (1 fps). Read both sheets for text styles and placement, caption style,
transitions and zooms. For a reel link in note.txt, download it if the link allows; otherwise work
from the notes and say so. Shared references are in `OVS Edit/References` (`drive.sh refs`,
read-only). Write what differs from house look as overrides in `edit.json` and in NOTES.md
("Reference match"), using the closest catalog blocks. Anything the reference doesn't show stays
house look. If the reference relies on something the house look avoids (heavy flash, shake,
dissolves), flag it in the storyboard instead of copying it silently.

## HOUSE LOOK
North star: Chris Boustedt (@chriss.boustedt). The values are mirrored in `style.json`. There is one
style system: restyled HyperFrames catalog blocks (CATALOG BLOCKS), never a second one.

### Format and length
- Vertical only: 1080×1920, 30 fps, H.264 (yuv420p) MP4.
- Aim for 30–45s unless note.txt or the inline notes say otherwise. Hard cap 45s unless the notes say
  otherwise.
- End fast with no outro. At most a ≤2s handle or CTA card.

### Vibe (from note.txt or the inline notes; otherwise ask once)
- **BOLD:** Inter Black caps captions at y≈1190, #FFD400 keyword blocks, chapter pills,
  text-behind-subject once per video.
- **CLEAN:** minimal captions, with giant text masked behind the subject (Chris Boustedt) as the main
  device.

### Hook (first 2–3s)
- The picture, the on-screen text and the first spoken line say the same thing. It works muted.
- No greetings and no intros. Start on the strongest line.
- Hook text: first words start at scale 2.4, blur 28px and 35% opacity, and go to scale 1, sharp and
  100% over 0.35s. Blurred and glow reveals are liked.
- Alternate hooks only on request: `scripts/build_hooks.sh` gives `<folder>_vN_hook-B.mp4`…, with
  only the first 1–3s swapped.

### Cutting and pacing
- Cut on word timings. Drop long silences, ums, false starts and repeated takes. Keep natural pauses
  and complete sentences, at natural voice speed (see step c).
- Something new on screen about every 1–2s (QA fails any hold over 2s). Get it from punch-ins,
  settles, B-roll, photos, graphics and layered text, not by chopping the speech.
- Talking head: slow zoom 1.00 → 1.08 (linear) across each take. Punch-ins 1.00 → 1.12 over 0.35s
  (power3.out). Scale-out settles 1.25 → 1.00 over 0.45s (power3.out).
- B-roll matches the spoken words and holds for about 3s at most, then it's back to the speaker.
  Montages cut every 0.5–0.7s.
- Footage: hard cuts. **Photo changes: a bounce transition, preferring scale-ins.** Avoid heavy
  flash and camera shake. One light flash on a hit only if Justin asks.
- Banned: dissolves, crossfades, spins, glitch packs, heavy flashes, camera shake.

### Captions and on-screen text (captions on by default)
- Centred, Inter Bold or heavier (Inter Black 900 for the BOLD talking-head look), ALL CAPS, 76px,
  white, a slight dark stroke, **no drop shadow**, no box. Centre at y≈1190.
- One word or a short phrase (≤3 words) at a time, popping in over 0.14s (back.out).
- Key words (numbers, names, payoff) sit in a solid #FFD400 block with black text and a 10px radius.
- **On-screen text changes only when the shot or photo changes**, never mid-shot or mid-photo. This
  covers titles, labels, pills, UI cards and photo text. Word captions follow speech, but a caption
  group never spans a cut.
- Clean layered animation on top of the talk (hook text, word captions, UI cards,
  text-behind-subject): dense but tidy, not basic.
- Hand-check these names in every transcript: **Mudex, One Vox Studio, Leederville**.

### Chapter pills (BOLD)
- #FFD400 pill, top-left at x120 y250, black Inter Black 28px caps. Changes each section, on a cut.

### Text behind subject
- BOLD: once per video, on the hero word. CLEAN: the main device, placed in the storyboard.
- One caps word in the heading face, auto-fit to ~92% of the frame width, centred around y≈620 so
  the head and hands cross it.
- Layers: footage → giant word → footage again, masked to the subject with a per-frame rembg matte
  (`scripts/matte.py`, `u2net_human_seg`).
- In: scale 1.18 → 1.00 over 0.35s, then a slow 4% drift.

### Headings
- Goal: Druk Wide (not licensed yet). Fallback: Archivo, width 125, weight 900. The font is a
  variable (`style.json` → `fonts.heading`); swap it there once licensed.

### Safe zone
- All text sits inside x 120–960, y 240–1260. Keep the bottom third clear for the platform UI.

### Graphics and effects
- Full-screen motion graphics follow the brief in step (d): brand colours/font, max 3 icons, one big
  headline, no small text, 2–3s, then back to the speaker.
- One pop-up graphic per mention, held ≤2s.
- Bold effects at most once every 5–10s, never two at once. At most 2 accent moments per video.

### Audio
- Voice peaks around −6 dBFS, at natural speed.
- Music only if it's commercially licensed. It fades under the words to −18…−22 dB, with no lyrics
  under speech. None exists yet: ship without music and say so. Never pull random tracks.
- SFX: a pop on small graphics only, never on full-screen overlays. A whoosh on whips.
  `Library/Sounds` has hit, tap and chime.

## CATALOG BLOCKS
Prefer HyperFrames catalog blocks (Free, v0.8.185) over building from scratch. Before hand-building
anything new, search the catalog first (`npx -y hyperframes@0.8.185 catalog --query "<what it should
do>"`). If something new is adopted, add it to `templates/ovs-vertical/blocks.txt` and give it a
restyle rule in `scripts/restyle_blocks.py`.

- **Template:** `templates/ovs-vertical/` (1080×1920) holds all 34 blocks, already restyled to the
  house look: Inter Black, #FFD400 accent with black text on it, Archivo width 125 for headings, text
  inside the safe zone, no text drop shadows. The restyle is a script, so it can be rebuilt from the
  catalog at any time with `scripts/install_blocks.sh` (reinstall + `scripts/restyle_blocks.py` +
  lint).
- **Mounting:** a block mounts with `data-composition-src="compositions/<name>.html"`. A component in
  `compositions/components/` has its markup, style and script merged into the scene. Some (e.g.
  `focus-blur-resolve`) only give their timeline recipe in a comment block.
- **Captions:** words come from `scripts/transcribe.py`. Replace the block's `WORDS` array and its
  groups (≤3 words). Mark key words (numbers, names, payoff) with `key: true`.

### Which block for each job
| Job | Default block | Alternates / notes |
| --- | --- | --- |
| Hook text (first 2–3s) | `focus-blur-resolve` (2.4× → 1×, blur 28px → 0, 35% → 100% opacity over 0.35s, phrase scales as one unit) | `blur-in`. For a single huge word: `caption-kinetic-slam` |
| Captions (default) | `caption-highlight` (white Inter Black 76px caps at y≈1190, 0.14s back.out pop, `key: true` words in a #FFD400 block) | "Karaoke" style → `caption-pill-karaoke`. "Word-pop" style → `caption-kinetic-slam` (one word at a time, big) |
| Text behind subject | `caption-parallax-layers` (hero word in Archivo 125/900, fitted to 92% width around y≈620, 1.18 → 1 over 0.35s then 4% drift). Put the rembg subject cutout (`scripts/matte.py`) on a layer above it | `mk-emphasis-type` for a low-contrast background word texture |
| Chapter pill | `spring-pop` holding the pill (top-left x120 y250) | |
| Lower third (name/role) | `lt-color-block` (yellow block, black Inter Black caps) | `lt-kicker-name`, `lt-bold-block`, `lt-stack-bars`; quieter: `lt-accent-underline`, `lt-side-rule`, `lt-clean-bar`, `lt-dark-card`, `lt-soft-pill`, `lt-mask-reveal`, `lt-neon-border` |
| Numbers / stat pop-ups | `number-pop-in` | `spring-pop` for a badge |
| Keyword hit (with the "pop" SFX) | `beat-accent` | |
| Photo change | Bounce scale-in on the new photo (the `spring-pop` overshoot), on the cut | Search the catalog before hand-building another |
| Typed text on screen | `typewriter` | `typed-prompt` (AI prompt), `notes-typing` (notes app) |
| Handwritten annotation | `hw-title` (word-by-word highlight) | `hw-write-title` (true write-on). Caveat stays: handwriting is the point |
| Transition (default) | Hard cut, with a punch-in 1.00 → 1.12 (0.35s power3.out) or a scale-out settle 1.25 → 1.00 (0.45s). `cut-the-curve` for a velocity-matched hard cut | `whip-pan-cut` for whips (add the whoosh; `Library/Transitions/whip-streak` fits) |
| Accent transition (counts toward the max of 2 accent moments) | `cinematic-zoom` (zoom blur) | `flash-through-white` / `Library/Transitions/flash-soft` only when Justin asks for a flash |
| Not house style unless asked | `glitch`, `chromatic-radial-split`, `Library/Transitions` film-burn and light-leaks | Installed, but used only if Justin asks for them by name |
| End | No outro. `cta-close` as a ≤2s CTA card | `logo-outro` only when asked, trimmed to ≤2s |

Known quirks:
- The 4 shader transitions (`cinematic-zoom`, `flash-through-white`, `glitch`,
  `chromatic-radial-split`) register under the composition id `main`, which clashes with a project's
  root id. Rename the id inside the block before mounting one.
- `caption-parallax-layers` refits the hero word on every timeline update, because the renderer can
  capture before the heading font has loaded. Don't remove that.

## DELIVERY CHECKLIST (every render, before it ships; `scripts/qa_check.py` covers the measurable lines)
- [ ] Storyboard stills approved by Justin before this render (revisions: the batch of notes applied).
- [ ] Hook in the first 2–3s (picture = on-screen text = first spoken line).
- [ ] Length 30–45s, or what the notes asked; never over 45s unless the notes say so.
- [ ] Something changes on screen at least every 2s.
- [ ] Natural pauses kept, sentences complete, voice at natural speed.
- [ ] Captions word-checked (incl. the names list), centred, inside the safe zone, no drop shadow.
- [ ] On-screen text changes only on a cut or photo change.
- [ ] No more than 2 accent moments.
- [ ] No watermarks.

## QA note (append to `projects/<folder>/NOTES.md` after each version)
Date, version, final length, hook line, what was cut, checklist results (pass/fail per line), anything
that needed judgement, and the Drive link(s).

## Layout
- `inbox/<folder>/`: media pulled for a job (git-ignored). Raw originals stay in Drive
  (1 Drop Clips) and aren't committed.
- `projects/<folder>/`: the editable project. It holds `transcript.json` (+ `transcripts/`),
  `plan.json`, `cuts.json`, `edit.json`, `storyboard/`, `index.html` + `compositions/`, `assets/`,
  `track.json`, `NOTES.md` and `renders/` (Git LFS).
- `templates/ovs-vertical/`: the restyled house template. `style.json` holds the house values.
- `done/artemis-soundbites/`: archived original from the old upload test.
- Retired: the Cutting Room Inbox artifact page (`ui/edit-inbox.html`), its `jobs`/`revisions` store,
  "process the inbox", `scripts/job_status.py`, `scripts/join_pieces.py` and
  `scripts/test_inbox_upload.mjs`. They're kept for history only. Don't queue, poll or update job
  cards.

## Environment notes
- The cloud container is ephemeral: always commit and push finished work. `scripts/setup.sh`
  reinstalls the toolchain (it runs from the SessionStart hook in `.claude/settings.json`).
- MP4/MOV/media are tracked with Git LFS (`.gitattributes`).
- Drive token: `RCLONE_DRIVE_TOKEN` (environment setting, loads at session start).
- Toolchain: HyperFrames CLI 0.8.185 (pinned) + headless Chrome, ffmpeg, faster-whisper (word
  timestamps), rembg with `u2net_human_seg` (subject mattes).
