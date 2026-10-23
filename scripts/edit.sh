#!/usr/bin/env bash
# One video, end to end: Drive folder in, reviewed render + HyperFrames project back in Drive.
#
#   scripts/edit.sh "<video name>" [--from a|b|c|d|e|f|g] [--only X] [--version N] [--no-upload]
#
#   a  pull     1 Drop Clips/<video>/ -> inbox/<slug>/ (rclone, resumable), note -> projects/<slug>/note.txt,
#               Drive Library/ (LUTs, Sounds, Music, Fonts, Logos, Transitions) -> library/
#   b  words    faster-whisper word timestamps for every clip -> transcript.json
#   c  plan     plan_cuts.py (uses plan.json if Claude wrote one) -> cuts.json
#   d  a-roll   build_aroll.py per format (seek-only reads, LUT, per-speaker crop, voice levelled)
#   e  project  build_comp.py per format -> projects/<slug>/<format>/: first the music bed (edit.json "music" or
#               studio.audio.track -> music.py -> assets/music.m4a, ducked under this A-roll), then the build, then a
#               people cutout per span in cutout.json (hero word + "behind" scenes, matte.py), then lint
#   f  render   npx hyperframes render, master.py (audio to -14 LUFS), qa.py (frames at 0s, 2s, middle, end -> qa/*.jpg)
#   g  upload   2 For Review/<video>_vN.mp4 (+ _vN_<format>.mp4) and 2 For Review/<video>_project/
#
# Revisions: change plan.json / edit.json, then `edit.sh "<video>" --from c` (or d/e) -> next _vN.
# Claude normally writes plan.json + edit.json after step b; without them the cut is automatic.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NAME="${1:?usage: edit.sh \"<video name>\" [--from X] [--only X] [--version N] [--no-upload]}"; shift
FROM=a; TO=g; VER=""; UPLOAD=1
while [ $# -gt 0 ]; do case "$1" in
  --from) FROM=$2; shift 2 ;; --only) FROM=$2; TO=$2; shift 2 ;;
  --version) VER=$2; shift 2 ;; --no-upload) UPLOAD=0; shift ;; *) echo "unknown option $1" >&2; exit 1 ;;
esac; done
SLUG=$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g')
RAW="inbox/$SLUG"; JOB="projects/$SLUG"; mkdir -p "$RAW" "$JOB"
run() { [[ ! "$1" < "$FROM" && ! "$1" > "$TO" ]]; }
say() { printf '\n== %s\n' "$*"; }
json() { python3 -c "import json,sys;d=json.load(open('$JOB/edit.json'));v=eval(sys.argv[1]);print(v if isinstance(v,str) else ' '.join(map(str,v)))" "$1"; }

if run a; then
  say "a. pull \"$NAME\" from Drive"
  scripts/drive.sh pull "$NAME" "$RAW"
  scripts/drive.sh library library/ || echo "(Library not synced)"
  note=$(find "$RAW" -maxdepth 1 -type f \( -iname '*.txt' -o -iname '*.rtf' -o -iname '*.md' \) | head -1)
  if [ -n "$note" ]; then
    python3 - "$note" "$JOB/note.txt" <<'PY'
import re, sys
s = open(sys.argv[1], errors="ignore").read()
if s.lstrip().startswith("{\\rtf"):  # plain text out of RTF (TextEdit's default)
    s = re.sub(r"\\par[d]?|\\\n", "\n", s)
    s = re.sub(r"\{\\\*[^{}]*\}|\{\\fonttbl[^}]*\}|\{\\colortbl[^}]*\}", "", s)
    s = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", s)
open(sys.argv[2], "w").write(re.sub(r"\n{3,}", "\n\n", s).strip() + "\n")
PY
    echo "note: $JOB/note.txt"; cat "$JOB/note.txt"
  fi
fi

CLIPS=$(find "$RAW" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.mxf' -o -iname '*.mkv' \) | sort)
[ -n "$CLIPS" ] || { echo "no clips in $RAW" >&2; exit 1; }

if run b; then
  say "b. transcribe"
  if [ -f "$JOB/transcript.json" ]; then echo "transcript.json exists (delete it to redo)"; else
    mapfile -t C <<<"$CLIPS"; python3 scripts/transcribe.py "$JOB/transcript.json" "${C[@]}"; fi
fi

if run c; then
  say "c. plan the cut"
  python3 scripts/plan_cuts.py "$JOB/transcript.json" "$JOB/cuts.json" --plan "$JOB/plan.json"
  [ -f "$JOB/edit.json" ] || python3 - "$JOB" <<'PY'
import json, sys
job = sys.argv[1]; takes = json.load(open(f"{job}/cuts.json"))["takes"]
hook = " ".join(w["w"] for w in takes[0]["words"]).rstrip(".,!?")
json.dump({"formats": ["9x16"], "hookText": hook, "hookKeys": [], "keys": [w["w"] for t in takes for w in t["words"] if any(c.isdigit() for c in w["w"])],
           "punch": [], "settle": [], "transition": {"look": "cut"}, "sfx": True, "tail": 0.3}, open(f"{job}/edit.json", "w"), indent=1)
print("wrote a default edit.json (hook = first line)")
PY
fi

FORMATS=$(json "d.get('formats', ['9x16'])")
LUT=$(json "d.get('lut') or ''")
if [ -z "$LUT" ]; then  # fall back to the studio style's LUT: built-in S-Log3 conversion or a file from Library/LUTs
  LUT=$(python3 -c "import json;g=json.load(open('style.json')).get('studio',{}).get('grade',{}).get('lut') or '';print({'none':'','slog3':'luts/slog3_to_709.cube'}.get(g, 'library/LUTs/'+g if g else ''))")
fi
[ -z "$LUT" ] || [ -f "$LUT" ] || { echo "LUT $LUT not found (put it in Drive: OVS Claude Edit/Library/LUTs)" >&2; exit 1; }

if run d; then
  for f in $FORMATS; do
    say "d. a-roll $f"; mkdir -p "$JOB/$f/assets"
    python3 scripts/build_aroll.py "$JOB/cuts.json" "$RAW" "$JOB/$f/assets/aroll.mp4" --format "$f" ${LUT:+--lut "$LUT"}
  done
fi

if run e; then
  for f in $FORMATS; do
    say "e. HyperFrames project $f"
    A="$JOB/$f/assets"; mkdir -p "$A"
    # music bed first, so build_comp mounts it: build_comp resolves the track and prints music.py's arguments ("" = no music)
    M=$(python3 scripts/build_comp.py "$JOB" --format "$f" --music-args) || M=""
    if [ -z "$M" ]; then
      rm -f "$A/music.m4a" "$A/music.args"
    else
      eval "MA=($M)"   # shlex-quoted by build_comp: track, voice (this A-roll), out, options
      if [ -f "$A/music.m4a" ] && [ "$A/music.m4a" -nt "$A/aroll.mp4" ] && [ "$A/music.m4a" -nt "${MA[0]}" ] && [ "$(cat "$A/music.args" 2>/dev/null)" = "$M" ]; then
        echo "music.m4a is current"
      elif python3 scripts/music.py "${MA[@]}"; then
        printf '%s\n' "$M" > "$A/music.args"
      else
        echo "warning: music bed failed (see above); going on without music" >&2; rm -f "$A/music.m4a" "$A/music.args"
      fi
    fi
    rm -f "$JOB/$f/cutout.json"
    python3 scripts/build_comp.py "$JOB" --format "$f"
    if [ -f "$JOB/$f/cutout.json" ]; then  # one cutout per span: cutout_<i>.webm + .span; an old single cutout.webm is reused if it matches
      while read -r F S E; do
        stamp="$A/${F%.webm}.span"
        if [ -f "$A/$F" ] && [ "$A/$F" -nt "$A/aroll.mp4" ] && [ "$(cat "$stamp" 2>/dev/null)" = "$S $E" ]; then
          echo "$F is current"
        elif [ "$F" != cutout.webm ] && [ -f "$A/cutout.webm" ] && [ "$A/cutout.webm" -nt "$A/aroll.mp4" ] && [ "$(cat "$A/cutout.span" 2>/dev/null)" = "$S $E" ]; then
          mv "$A/cutout.webm" "$A/$F" && mv "$A/cutout.span" "$stamp" && echo "$F: reused the old cutout.webm"
        else
          python3 scripts/matte.py "$A/aroll.mp4" "$A/$F" --start "$S" --end "$E" </dev/null && echo "$S $E" > "$stamp"
        fi
      done < <(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));[print(s.get('file','cutout.webm'),s['start'],s['end']) for s in d.get('spans',[d])]" "$JOB/$f/cutout.json")
    fi
    (cd "$JOB/$f" && npx --yes hyperframes lint)
  done
fi

if [ -z "$VER" ]; then
  if [ "$UPLOAD" = 1 ]; then VER=$(scripts/drive.sh next "$NAME"); else VER=$(ls "$JOB/renders" 2>/dev/null | sed -nE 's/.*_v([0-9]+)_.*/\1/p' | sort -n | tail -1); VER=$(( ${VER:-0} + 1 )); fi
fi

if run f; then
  mkdir -p "$JOB/renders"
  for f in $FORMATS; do
    say "f. render v$VER $f"
    (cd "$JOB/$f" && npx --yes hyperframes render -q delivery -o "../renders/${SLUG}_v${VER}_$f.mp4" --quiet)
    python3 scripts/master.py "$JOB/renders/${SLUG}_v${VER}_$f.mp4"   # the mix to -14 LUFS / -1.5 dBTP, picture untouched
    python3 scripts/qa.py "$JOB/renders/${SLUG}_v${VER}_$f.mp4" "$JOB" --format "$f" || echo "QA: see failures above"
  done
fi

if run g && [ "$UPLOAD" = 1 ]; then
  say "g. upload to 2 For Review"
  first=1
  for f in $FORMATS; do
    if [ $first = 1 ]; then dest="${NAME}_v${VER}.mp4"; first=0; else dest="${NAME}_v${VER}_$f.mp4"; fi
    echo "$dest: $(scripts/drive.sh push "$JOB/renders/${SLUG}_v${VER}_$f.mp4" "$dest")"
  done
  echo "${NAME}_project/: $(scripts/drive.sh push-project "$JOB" "$NAME")"
fi
say "done: $NAME v$VER"
