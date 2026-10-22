#!/usr/bin/env bash
# Reinstalls the editing toolchain in a fresh cloud container. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
HF_VERSION=0.8.185

python3 -c "import faster_whisper, rembg" 2>/dev/null || pip install -q faster-whisper "rembg[cpu]"
npx -y "hyperframes@${HF_VERSION}" browser ensure >/dev/null
# Pre-fetch models so the first job doesn't stall on downloads.
python3 - <<'PY'
from rembg import new_session
new_session("u2net_human_seg")
from faster_whisper import WhisperModel
WhisperModel("small.en", device="cpu", compute_type="int8")
PY
echo "editing toolchain ready"
