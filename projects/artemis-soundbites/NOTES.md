# Artemis soundbites (upload test) — v1

End-to-end test of the Cutting Room Inbox upload route with a 544 MB .mov, edited in house style.

## Source
- `artemis_soundbites.mov`, 543,591,879 bytes, sha256 `a76d0b51…a07d`, 6:28, 1920x1080 29.97 fps.
  Re-encode of NASA "Artemis Media Resource – Interview Soundbites" (images.nasa.gov, public domain).
- Original kept in `done/artemis-soundbites/` (Git LFS, confirmed on the remote).
- Speaker: no on-screen name slate, so the lower third uses only what the footage shows
  ("NASA Artemis / Interview soundbite · 2019"). Not named in captions.

## Upload route test
1. The page's own upload code (headless Chromium, `scripts/test_inbox_upload.mjs`): 39 pieces
   (38 × 14,000,001 B + 11,591,880 B), job doc built and queued; rejoined sha256 = original.
2. Same pieces into the artifact's real asset store (39 uploads), job doc `jobs/t544-artemis` in the
   real db; pulled back piece by piece and rejoined: sha256 = original.
3. Break found: Artifact `read` with bulk `paths` doesn't reach assets → read one `path` per piece.
4. Not covered: a browser upload from Justin's signed-in session (needs a person at the page).
5. Storage auto-freed after the LFS check: all 39 pieces deleted.

## Edit (v1)
- Teaching clip, 27.8 s, 15 takes, word-accurate cuts (pauses > 0.28 s and "of course" removed).
- Hook: "the moon is the way to get to Mars" / text "THE MOON IS THE WAY TO MARS" (MARS in yellow).
- Chapters: WHY THE MOON → THE ROCKET → THE GOAL.
- Hero word (text behind subject): FUEL, Archivo 125/900 at 92% width, rembg u2net_human_seg cutout
  over it. About 40% covered by the head (the E is hidden); "ROCKET FUEL." caption directly below.
- B-roll (NASA, public domain): LROC lunar south pole, Clementine south pole, Artemis I SLS on the
  pad, Mars (Viking mosaic) — each on its spoken mention, ≤ 2 s.
- Punch-ins on "moon" / "rocket" / "proving ground", settles on the first body cut and "taking".
- Audio: voice levelled to −5.7 dBFS peaks; synthesized whoosh/pop SFX; **no music** (none licensed).

## Alternate hooks (first 1–3 s only)
- B: "So the moon is the proving ground"
- C: "but it's also rocket fuel"
- D: "the largest, most powerful rocket ever launched"
- E: "a sustainable return to the moon"

## Fixes made during the test
- QA caught a 2.2 s hold with no visual change (sound effects had been counted as visual events).
  Fixed the checker and the edit (punch-ins on "moon" and "rocket", a second Moon still on "water ice").
- The lower third hid under a B-roll still; moved to the "life support" take and pinned its layer.
- Hero word size is computed offline from the real font (the renderer can't measure at render time).

## QA (v1)
2026-10-22 · v1 · 27.8 s · QA 7/7
- [x] Hook on frame 1 (visual = text = first line) — text “The moon is the way to Mars” vs spoken “the moon is the way to get to mars” (100% shared); speech starts 0.06s; text fully resolved by 0.35s
- [x] Length within target — 27.8s, teaching target 15–45s
- [x] A change on screen every 2s or less — longest hold 1.88s at 22.57s (cuts, punch-ins, B-roll, graphics; captions not counted)
- [x] Captions word-checked and inside the safe zone — caption line y≈1190, x 120–960; names list checked (Mudex, One Vox Studio, Leederville: none spoken)
- [x] At most 2 accent moments — 1 (text-behind-subject on “Fuel”)
- [x] No watermarks — no logos or watermarks added; source and B-roll are public-domain NASA media
- [x] 4 alternate-hook versions exported — 4 rendered (first 1–3s swapped)

Delivery: renders in `renders/` (repo, Git LFS). Drive upload to 2 For Review pending the rclone token
(not visible in this session). Job card updated with preview, hooks, QA and notes.
