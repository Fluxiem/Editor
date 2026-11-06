#!/usr/bin/env bash
# Drive transfers for "OVS Claude Edit" via rclone (no size limit). Folder IDs come from style.json.
# Needs rclone and RCLONE_DRIVE_TOKEN (the JSON from `rclone authorize "drive"`, saved in the environment).
#
#   drive.sh scan                          list 1 Drop Clips folders with no <folder>_vN.mp4 yet (list only)
#   drive.sh pull <folder> <dir>           copy 1 Drop Clips/<folder>/ to <dir> (refuses cancelled/stopped jobs)
#   drive.sh push <file.mp4>               upload a render to 2 For Review
#   drive.sh push-project <dir> <folder>   upload an editable HyperFrames project to 2 For Review/<folder>_project/
#   drive.sh review                        list 2 For Review
#   drive.sh approve <file.mp4>            move that render from 2 For Review to 3 Approved (raw clips stay)
#   drive.sh broll [<file> <dir>]          list (or copy one file from) OVS Edit/B-Roll, read-only
#   drive.sh refs [<file> <dir>]           list (or copy one file from) OVS Edit/References, read-only
#   drive.sh library [<path> <dir>]        list (or copy from) OVS Claude Edit/Library
#
# Raw clips in 1 Drop Clips are never deleted by this script. Never touches the Grok team's
# "OVS Edit" inbox/review/approved folders (only its B-Roll and References, read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v rclone >/dev/null || { echo "rclone not installed (scripts/setup.sh installs it)" >&2; exit 2; }
: "${RCLONE_DRIVE_TOKEN:?RCLONE_DRIVE_TOKEN is not set: it is saved in the environment settings and loads at session start}"
export RCLONE_CONFIG_OVS_TYPE=drive RCLONE_CONFIG_OVS_SCOPE=drive RCLONE_CONFIG_OVS_TOKEN="$RCLONE_DRIVE_TOKEN"
id() { python3 -c "import json,sys;d=json.load(open('$ROOT/style.json'))['drive'];print(d[sys.argv[1]]['id'])" "$1"; }
INBOX=$(id inbox); REVIEW=$(id review); APPROVED=$(id approved); LIBRARY=$(id library)
BROLL=$(id sharedBroll); REFS=$(id sharedReferences)
IGNORE=$(python3 -c "import json;print('\n'.join(json.load(open('$ROOT/style.json'))['drive'].get('ignoreJobs',[])))")
at() { local folder=$1; shift; rclone "$@" --drive-root-folder-id "$folder"; }
videos_with_render() { at "$1" lsf ovs: --files-only --include "*.mp4" | sed -E 's/_v[0-9]+(_[A-Za-z0-9x-]+)?\.mp4$//' | sort -u; }
readonly_get() { if [ $# -ge 3 ]; then at "$1" copy "ovs:$2" "$3" --progress; else at "$1" lsf ovs: -R; fi; }

case "${1:-}" in
  scan)
    done_list=$(videos_with_render "$REVIEW"; videos_with_render "$APPROVED")
    at "$INBOX" lsf ovs: --dirs-only | sed 's#/$##' | while read -r v; do
      grep -qxF "$v" <<<"$IGNORE" && continue
      grep -qxF "$v" <<<"$done_list" || echo "$v"
    done ;;
  pull)
    if grep -qxF "$2" <<<"$IGNORE" && [ "${4:-}" != "--justin-approved-restart" ]; then
      echo "'$2' is a cancelled/stopped job (style.json drive.ignoreJobs). Not pulling without Justin's explicit OK." >&2; exit 3
    fi
    at "$INBOX" copy "ovs:$2" "$3" --progress ;;
  push)         at "$REVIEW" copy "$2" ovs: --progress ;;
  push-project) at "$REVIEW" copy "$2" "ovs:$3_project" --progress ;;
  review)       at "$REVIEW" lsf ovs: ;;
  approve)   # drive.sh approve <file.mp4> [--dry-run]
    f=$(basename "$2")
    at "$REVIEW" lsf ovs: --files-only | grep -qxF "$f" || { echo "not in 2 For Review: $f" >&2; exit 4; }
    for r in REV:"$REVIEW" APP:"$APPROVED"; do
      export "RCLONE_CONFIG_${r%%:*}_TYPE=drive" "RCLONE_CONFIG_${r%%:*}_SCOPE=drive" \
             "RCLONE_CONFIG_${r%%:*}_TOKEN=$RCLONE_DRIVE_TOKEN" "RCLONE_CONFIG_${r%%:*}_ROOT_FOLDER_ID=${r#*:}"
    done
    rclone moveto "REV:$f" "APP:$f" --drive-server-side-across-configs ${3:+"$3"}
    [ "${3:-}" = "--dry-run" ] || echo "moved $f to 3 Approved (raw clips in 1 Drop Clips untouched)" ;;
  broll)   shift; readonly_get "$BROLL" "$@" ;;
  refs)    shift; readonly_get "$REFS" "$@" ;;
  library) shift; readonly_get "$LIBRARY" "$@" ;;
  *) sed -n '2,16p' "$0"; exit 1 ;;
esac
