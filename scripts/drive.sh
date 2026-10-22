#!/usr/bin/env bash
# Google Drive "OVS Claude Edit" via rclone (no size limit, resumable). Folder IDs are in style.json -> drive.
# Needs rclone and RCLONE_DRIVE_TOKEN (the JSON from `rclone authorize "drive"`, set in the environment).
#
#   drive.sh list                       video folders waiting in 1 Drop Clips (no render in 2 For Review / 3 Approved yet)
#   drive.sh pull <video> <dir>         copy 1 Drop Clips/<video>/ to <dir> (skips files already there)
#   drive.sh next <video>               next free version number for <video> (1 if none yet)
#   drive.sh push <file> <name>         upload <file> to 2 For Review/<name>; prints its Drive link
#   drive.sh push-project <dir> <video> mirror <dir> to 2 For Review/<video>_project/
#   drive.sh approve <video>            move the latest <video>_vN renders to 3 Approved, delete 1 Drop Clips/<video>/
#   drive.sh library <dir>              copy OVS Claude Edit/Library/ (LUTs, Sounds, Music, Fonts, Logos) to <dir>
#
# Never touches the Grok team's "OVS Edit" folders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v rclone >/dev/null || { echo "rclone not installed (scripts/setup.sh installs it)" >&2; exit 2; }
: "${RCLONE_DRIVE_TOKEN:?RCLONE_DRIVE_TOKEN is not set (environment setting, loads at session start)}"
export RCLONE_CONFIG_OVS_TYPE=drive RCLONE_CONFIG_OVS_SCOPE=drive RCLONE_CONFIG_OVS_TOKEN="$RCLONE_DRIVE_TOKEN"
export RCLONE_DRIVE_CHUNK_SIZE=64M RCLONE_LOG_LEVEL=ERROR
id() { python3 -c "import json,sys;print(json.load(open('$ROOT/style.json'))['drive'][sys.argv[1]]['id'])" "$1"; }
ROOTID=$(id root); INBOX=$(id inbox); REVIEW=$(id review); APPROVED=$(id approved)
at() { local folder=$1; shift; rclone "$@" --drive-root-folder-id "$folder"; }
versions() { at "$1" lsf ovs: --files-only --include "*.mp4" | sed -nE "s/^$(printf '%s' "$2" | sed 's/[][\.*^$/]/\\&/g')_v([0-9]+).*\.mp4$/\1/p" | sort -n; }
link() { at "$REVIEW" lsjson "ovs:$1" | python3 -c "import json,sys;d=json.load(sys.stdin);print('https://drive.google.com/file/d/'+d[0]['ID']+'/view' if d else '')"; }

case "${1:-}" in
  list)
    at "$INBOX" lsf ovs: --dirs-only | sed 's#/$##' | while read -r v; do
      [ -z "$(versions "$REVIEW" "$v")$(versions "$APPROVED" "$v")" ] && echo "$v"
    done; true ;;
  pull)  at "$INBOX" copy "ovs:$2" "$3" --transfers 4 --checkers 8 --stats 15s --stats-one-line --stats-log-level NOTICE ;;
  next)  last=$( (versions "$REVIEW" "$2"; versions "$APPROVED" "$2") | sort -n | tail -1); echo $(( ${last:-0} + 1 )) ;;
  push)  at "$REVIEW" copyto "$2" "ovs:$3"; link "$3" ;;
  push-project)
    at "$REVIEW" sync "$2" "ovs:$3_project" --exclude ".hyperframes/**" --exclude "node_modules/**" --exclude ".work-*/**" --exclude "*/.work-*/**"
    at "$REVIEW" lsjson ovs: --dirs-only | python3 -c "import json,sys;n=sys.argv[1];print(next(('https://drive.google.com/drive/folders/'+d['ID'] for d in json.load(sys.stdin) if d['Name']==n),''))" "$3_project" ;;
  approve)
    v=$(versions "$REVIEW" "$2" | tail -1); [ -n "$v" ] || { echo "no $2_vN render in 2 For Review" >&2; exit 1; }
    at "$REVIEW" lsf ovs: --files-only --include "$2_v${v}*.mp4" | while read -r f; do
      rclone moveto "ovs:2 For Review/$f" "ovs:3 Approved/$f" --drive-root-folder-id "$ROOTID" && echo "approved: 3 Approved/$f"
    done
    at "$INBOX" purge "ovs:$2" && echo "deleted raw clips: 1 Drop Clips/$2" ;;
  library) rclone copy "ovs:Library" "$2" --transfers 4 --drive-root-folder-id "$ROOTID" ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
