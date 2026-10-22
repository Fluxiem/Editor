# Editor — autonomous HyperFrames video editing

Claude acts as an autonomous video editor for this repo. Skills live in `.claude/skills/`
(hyperframes, hyperframes-cli, hyperframes-registry, media-use, …) — load the relevant ones
before building.

## Layout
- `inbox/` — drop clips, folders, references, or a `brief.md` here. Each top-level item
  (or subfolder) = one job; loose files at the root of `inbox/` = one job together.
- `projects/<job-slug>/` — the editable HyperFrames project for each job (compositions,
  assets, transcripts, `NOTES.md` with decisions + edit log).
- `done/<job-slug>/` — original source media moved here after a job finishes, plus
  `<job-slug>.mp4` (final render).

## Web inbox (Cutting Room Inbox)
Artifact: https://claude.ai/artifact/G5w5iJcPT376URSdZ11hmZ (source: `ui/edit-inbox.html`).
- Jobs live in its db collection `jobs` (fields: name, format, captions, length, brief, keep,
  links[], files[{name,size,type,pieceSize,chunks[]}], status, note, output, outputPath, createdAt).
- Every file is uploaded as ordered pieces (asset ids in `chunks`): each piece = one 0x00
  header byte + up to 19 MiB of the original. Storage is 1 GB per artifact in total.
- "Process the inbox": `ArtifactData list jobs`, take `status == "queued"`, download every
  piece with `Artifact read paths=[...ids]`, rebuild each file with
  `scripts/join_pieces.py inbox/<job-slug>/<name> <piece files in chunks order>`, verify the size,
  fetch links (Drive via the Google Drive connector), then run the job workflow below.
- Once a job is rendered, the page shows a "Free storage" button; the user clicks it to delete
  that job's pieces (originals stay in `done/`). Don't delete pieces yourself unless asked.
- Update the job doc as you go: status `editing` → `rendered` (or `needs-input` with a
  question in `note`). Put a short summary in `note`, the repo path in `outputPath`, and
  upload the MP4 as an asset (`Artifact publish asset:true`, ≤15 MB) into `output` so it
  plays on the page.
- Jobs over ~1 GB total come in as Google Drive links.

## Job workflow
1. Inspect every file (ffprobe, keyframe snapshots, transcribe speech, read briefs/references).
2. Decide format/aspect, style, pacing, captions, graphics, structure; write them to `NOTES.md`.
3. Scaffold/update the HyperFrames project (`npx hyperframes init`, pinned version).
4. Build: cut dead air/silences, captions, graphics, music, match references.
5. `npx hyperframes check`, snapshot key frames and review, then `npx hyperframes render`.
6. Move sources from `inbox/` to `done/<job-slug>/`, copy the MP4 there, commit + push.
7. Report output path + short summary.

Only ask the user when truly blocked (missing critical asset, unclear must-keep moment).

## Feedback iterations
"Tighter", "change caption style", etc. → edit the project in `projects/<job-slug>/`,
re-render, overwrite the MP4 in `done/`, log the change in `NOTES.md`. No Studio needed.

## Environment notes
- Cloud container is ephemeral: always commit + push finished work.
- MP4/MOV/media are tracked with Git LFS (`.gitattributes`).
- Headless Chrome: `npx hyperframes browser ensure`. Transcription needs whisper
  (install faster-whisper or whisper.cpp on first captions job).
