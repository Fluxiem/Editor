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
