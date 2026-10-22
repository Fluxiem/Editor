# Mudex: Driftability

Source: `1 Drop Clips/Mudex: Driftability/C6805.MP4` (Sony, 1920×1080 23.976, S-Log3, 1:43, 640 MB)
plus `Mudex Driftability.rtf` (note → `note.txt`). Three people in the Mudex warehouse: the Mudex
staff in hi-vis (left, right) and the Driftability organiser (middle, black tee).

## v1 (2026-10-22)

- Formats: 9:16 cropped to whoever is speaking (`focus` per line in plan.json) and the 16:9 frame as
  shot. Both graded with `luts/slog3_to_709.cube` (S-Log3/S-Gamut3.Cine → Rec709).
- Length 31.5s (from 1:43). 12 takes.
- Hook (0–2.4s, middle): "These events can't happen without the help" on screen as it is said.
- Order: hook → "…from Mudex as well as our other supporters" → "So that time of year again, we've got
  Driftability on" (DRIFTABILITY behind the speaker, rembg cutout) → "2nd of November, sold out event
  already" → "It's pretty easy to see why, I kept an eye on those nominations…" → "we can't help
  everybody but we do as much as we can" → "It's a great event, we're really proud to be part of it" →
  "what we do is the easy part and what you guys do is the hard part" (punch-in) → "as it gets bigger
  and better… a couple of events a year" (settle) → "it's certainly something on the cards" →
  "thank you very much and looking forward to it".
- Cut: the burnouts / push bike / 200 Series banter, "we've had a couple of little things trip us up",
  the waiting-list back-and-forth, the repeated thank-yous, one 0.46s pause and a "we we" false start.
- Captions: Inter Black caps, 3 words max, key words in the yellow block (Mudex, Driftability,
  November, sold, nominations, everybody, proud, hard, couple, cards). No SFX (clean corporate piece).

### Judgement calls
- Whisper heard "from the both users"; captioned as **Mudex** (likely "the Mudex boys"). "do AI" is
  captioned "see why". Both worth a listen.
- No Driftability logo file was in the folder or anywhere in Drive, so the behind-the-subject element
  is the word DRIFTABILITY in the house heading face. Drop the logo (PNG with transparency) into
  `Library/Logos` and set `edit.json` → `hero.logo` to swap it in.
- The caption style reference is a LinkedIn post (login-only), so captions follow the note (Inter
  Black) and house style.

### QA
- 9:16 and 16:9: 1080×1920 / 1920×1080 @ 30 fps, H.264 yuv420p, 31.6s, audio peak −5.7 dBFS, hook on
  frame 1; frames at 0s, 2s, middle, end checked (`qa/`).
