#!/usr/bin/env bash
# Render alternate-hook versions: only the opening (hook) take and hook text change.
#   build_hooks.sh PROJECT_DIR SOURCE NAME   (reads PROJECT_DIR/hooks.json, plan.json, edit.json)
set -euo pipefail
P="$(cd "$1" && pwd)"; SRC="$2"; NAME="$3"; S="$(cd "$(dirname "$0")" && pwd)"
for id in $(python3 -c "import json;print(' '.join(h['id'] for h in json.load(open('$P/hooks.json'))))"); do
  V="$P/hooks/hook-$id"; mkdir -p "$V/assets"
  cp -r "$P/assets/broll" "$V/assets/"; cp "$P/assets/hero_cutout.webm" "$V/assets/"
  python3 - "$P" "$V" "$id" <<'PY'
import json, sys
P, V, hid = sys.argv[1:]
h = next(x for x in json.load(open(f"{P}/hooks.json")) if x["id"] == hid)
plan = json.load(open(f"{P}/plan.json")); edit = json.load(open(f"{P}/edit.json"))
plan["segments"][0] = {"id": "hook", "role": "hook", "phrase": h["phrase"], "near": h["near"]}
edit["hookText"], edit["hookKeys"] = h["text"], h["keys"]
json.dump(plan, open(f"{V}/plan.json", "w"), indent=1); json.dump(edit, open(f"{V}/edit.json", "w"), indent=1)
PY
  python3 "$S/cutlist.py" "$P/transcript.json" "$V/plan.json" "$V/cuts.json" > "$V/cutlist.log"
  python3 "$S/build_aroll.py" "$SRC" "$V/cuts.json" "$P/track.json" "$V/assets/aroll.mp4"
  python3 "$S/build_comp.py" "$V" "$V/cuts.json" "$V/edit.json"
  (cd "$V" && npx -y hyperframes@0.8.185 render -o "$P/renders/${NAME}_hook-$id.mp4" --fps 30 --quality looks --strict --quiet)
  echo "DONE hook-$id"
done
