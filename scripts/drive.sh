#!/usr/bin/env bash
# Large-file Drive transfers (the connector caps downloads at 10 MB).
# Needs rclone and an RCLONE_DRIVE_TOKEN environment variable (the JSON from `rclone authorize "drive"`).
#   drive.sh ls   <folder-id>
#   drive.sh get  <folder-id> <name> <local-dir>
#   drive.sh put  <local-file> <folder-id>
set -euo pipefail
command -v rclone >/dev/null || { echo "rclone not installed" >&2; exit 2; }
: "${RCLONE_DRIVE_TOKEN:?RCLONE_DRIVE_TOKEN is not set: add it in the environment settings}"
export RCLONE_CONFIG_OVS_TYPE=drive RCLONE_CONFIG_OVS_SCOPE=drive RCLONE_CONFIG_OVS_TOKEN="$RCLONE_DRIVE_TOKEN"
case "$1" in
  ls)  rclone lsf --drive-root-folder-id "$2" ovs: ;;
  get) rclone copy --drive-root-folder-id "$2" "ovs:$3" "$4" --progress ;;
  put) rclone copy "$2" --drive-root-folder-id "$3" ovs: --progress ;;
  *) echo "usage: drive.sh ls|get|put ..." >&2; exit 1 ;;
esac
