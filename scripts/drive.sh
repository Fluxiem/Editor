#!/usr/bin/env bash
# Drive transfers for "OVS Claude Edit" via rclone (no size limit). Folder IDs come from style.json.
# Needs rclone and RCLONE_DRIVE_TOKEN (the JSON from `rclone authorize "drive"`, saved in the environment).
#
#   drive.sh scan                      subfolders of 1 Drop Clips with no <video>_vN.mp4 in 2 For Review
#   drive.sh pull <video> <dir>        copy 1 Drop Clips/<video>/ to <dir>
#   drive.sh broll [<file> <dir>]      list (or copy one file from) OVS Edit/B-Roll, read-only
#   drive.sh push <file.mp4>           upload a render to 2 For Review
#   drive.sh review                    list renders in 2 For Review
#   drive.sh cleanup [--dry-run]       delete raw 1 Drop Clips/<video>/ once <video>_vN.mp4 is in 3 Approved
#
# Never touches the Grok team's "OVS Edit" folders (only its B-Roll, read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v rclone >/dev/null || { echo "rclone not installed (scripts/setup.sh installs it)" >&2; exit 2; }
: "${RCLONE_DRIVE_TOKEN:?RCLONE_DRIVE_TOKEN is not set: it is saved in the environment settings and loads at session start}"
export RCLONE_CONFIG_OVS_TYPE=drive RCLONE_CONFIG_OVS_SCOPE=drive RCLONE_CONFIG_OVS_TOKEN="$RCLONE_DRIVE_TOKEN"
id() { python3 -c "import json,sys;d=json.load(open('$ROOT/style.json'))['drive'];print(d[sys.argv[1]]['id'])" "$1"; }
INBOX=$(id inbox); REVIEW=$(id review); APPROVED=$(id approved); BROLL=$(id sharedBroll)
IGNORE=$(python3 -c "import json;print('\n'.join(json.load(open('$ROOT/style.json'))['drive'].get('ignoreJobs',[])))")
at() { local folder=$1; shift; rclone "$@" --drive-root-folder-id "$folder"; }
videos_with_render() { at "$1" lsf ovs: --files-only --include "*.mp4" | sed -E 's/_v[0-9]+(_hook-[A-Z])?\.mp4$//' | sort -u; }

case "${1:-}" in
  scan)
    done_list=$(videos_with_render "$REVIEW"; videos_with_render "$APPROVED")
    at "$INBOX" lsf ovs: --dirs-only | sed 's#/$##' | while read -r v; do
      grep -qxF "$v" <<<"$IGNORE" && continue
      grep -qxF "$v" <<<"$done_list" || echo "$v"
    done ;;
  pull)  at "$INBOX" copy "ovs:$2" "$3" --progress ;;
  broll) if [ $# -ge 3 ]; then at "$BROLL" copy "ovs:$2" "$3" --progress; else at "$BROLL" lsf ovs: --files-only; fi ;;
  push)  at "$REVIEW" copy "$2" ovs: --progress ;;
  review) at "$REVIEW" lsf ovs: --files-only ;;
  cleanup)
    approved=$(videos_with_render "$APPROVED")
    at "$INBOX" lsf ovs: --dirs-only | sed 's#/$##' | while read -r v; do
      grep -qxF "$v" <<<"$approved" || continue
      if [ "${2:-}" = "--dry-run" ]; then echo "would delete 1 Drop Clips/$v"; else at "$INBOX" purge "ovs:$v" && echo "deleted 1 Drop Clips/$v"; fi
    done ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
