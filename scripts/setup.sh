#!/usr/bin/env bash
# Reinstalls the editing toolchain in a fresh cloud container. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
HF_VERSION=0.8.185

python3 -c "import faster_whisper, rembg" 2>/dev/null || pip install -q faster-whisper "rembg[cpu]"
npx -y "hyperframes@${HF_VERSION}" browser ensure >/dev/null
# rclone for Drive transfers (scripts/drive.sh): streams any file size, resumable
if ! command -v rclone >/dev/null; then
  tmp=$(mktemp -d) && curl -sSfL -o "$tmp/rclone.zip" https://downloads.rclone.org/rclone-current-linux-amd64.zip \
    && unzip -qo "$tmp/rclone.zip" -d "$tmp" && install -m 755 "$tmp"/rclone-*-linux-amd64/rclone /usr/local/bin/rclone; rm -rf "$tmp"
fi
# Pre-fetch models so the first job doesn't stall on downloads.
python3 - <<'PY'
from rembg import new_session
new_session("u2net_human_seg")
from faster_whisper import WhisperModel
WhisperModel("medium.en", device="cpu", compute_type="int8")
PY
echo "editing toolchain ready"
